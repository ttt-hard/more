# E2E verification for the Langfuse integration.
#
# Flow:
#   1. POST /api/workspaces/open to activate a known workspace on the running backend
#   2. POST /api/conversations to create a throwaway conversation (gives us a conversation_id)
#   3. GET  /api/conversations/{id}/stream?prompt=... to trigger a full agent turn (SSE)
#   4. Sleep a few seconds so the Langfuse SDK's background flusher can upload
#   5. GET https://cloud.langfuse.com/api/public/traces to inspect the freshest trace
#   6. Print whether that trace has a non-empty session_id (the signal we're after)
#
# Usage:
#   pwsh -File .\scripts\verify_langfuse.ps1
#
# Env overrides (optional):
#   BACKEND_URL, WORKSPACE_PATH, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
param(
    [string]$BackendUrl   = $(if ($env:BACKEND_URL)   { $env:BACKEND_URL }   else { "http://127.0.0.1:8000" }),
    [string]$WorkspacePath = $(if ($env:WORKSPACE_PATH) { $env:WORKSPACE_PATH } else { "d:\more\workspace" }),
    [string]$Prompt       = "langfuse e2e probe ping",
    [int]$FlushWaitSec    = 6
)

$ErrorActionPreference = "Stop"

function Show-Section($title) {
    Write-Host ""
    Write-Host ("=== " + $title + " ===") -ForegroundColor Cyan
}

# --- 1. open workspace -----------------------------------------------------
Show-Section "Open workspace: $WorkspacePath"
$openBody = @{ root_path = $WorkspacePath } | ConvertTo-Json -Compress
$openResp = Invoke-RestMethod -Uri "$BackendUrl/api/workspaces/open" `
    -Method POST -ContentType "application/json" -Body $openBody -TimeoutSec 15
Write-Host ("workspace_id=" + $openResp.workspace.id)

# --- 2. create throwaway conversation --------------------------------------
Show-Section "Create conversation"
$createResp = Invoke-RestMethod -Uri "$BackendUrl/api/conversations" `
    -Method POST -ContentType "application/json" -Body "{}" -TimeoutSec 15
$convId = $createResp.id
if (-not $convId) { $convId = $createResp.conversation.id }
Write-Host ("conversation_id=" + $convId)

# --- 3. trigger the SSE stream (one full agent turn) -----------------------
Show-Section "Trigger stream (SSE, full turn)"
$encodedPrompt = [uri]::EscapeDataString($Prompt)
$streamUrl = "$BackendUrl/api/conversations/$convId/stream?prompt=$encodedPrompt"
Write-Host ("GET " + $streamUrl)
# Run in a blocking fashion so we know the turn finished before we probe Langfuse.
$streamResp = Invoke-WebRequest -Uri $streamUrl -Method GET -TimeoutSec 120 -UseBasicParsing
Write-Host ("status=" + $streamResp.StatusCode + "  bytes=" + $streamResp.Content.Length)

# --- 4. poll the Langfuse cloud until the trace carries sessionId ---------
# Langfuse's ingestion pipeline lags: a trace posted via `POST /api/public/ingestion`
# shows up in `GET /api/public/traces` almost immediately, but its derived fields
# (sessionId, tags, ...) take another aggregation pass — empirically 10-20 seconds
# on cloud-hosted tier. So we poll the traces list and bail as soon as we find
# the one we just created with the expected sessionId, up to $PollTimeoutSec.
Show-Section "Query Langfuse cloud"
$pk = if ($env:LANGFUSE_PUBLIC_KEY) { $env:LANGFUSE_PUBLIC_KEY } else { "pk-lf-f3fc55f6-226f-4c58-b497-ec158e69fadd" }
$sk = if ($env:LANGFUSE_SECRET_KEY) { $env:LANGFUSE_SECRET_KEY } else { "sk-lf-178f406e-7ed9-4a57-aac7-1a24920d8545" }
$host_ = if ($env:LANGFUSE_HOST)   { $env:LANGFUSE_HOST }    else { "https://cloud.langfuse.com" }

$pair = "${pk}:${sk}"
$b64 = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes($pair))
$headers = @{ Authorization = "Basic $b64" }

$tracesUri = "$host_/api/public/traces?limit=15"
$pollTimeoutSec = 45
$pollIntervalSec = 3
$deadline = (Get-Date).AddSeconds($pollTimeoutSec)
$convTurn = $null
$attempt = 0
do {
    $attempt++
    Start-Sleep -Seconds $pollIntervalSec
    $tracesResp = Invoke-RestMethod -Uri $tracesUri -Headers $headers -Method GET -TimeoutSec 20
    $convTurn = $tracesResp.data | Where-Object { $_.sessionId -eq $convId } | Select-Object -First 1
    Write-Host ("  attempt " + $attempt + ": total=" + $tracesResp.meta.totalItems + "  match=" + [bool]$convTurn)
    if ($convTurn) { break }
} while ((Get-Date) -lt $deadline)

Write-Host ""
$tracesResp.data | Select-Object -First 10 @{n='time';e={($_.timestamp -split 'T')[1].Substring(0,8)}}, name, sessionId, id |
    Format-Table -AutoSize

Show-Section "Verdict"
if ($convTurn) {
    Write-Host ("PASS: found trace with session_id=" + $convTurn.sessionId + "  name=" + $convTurn.name) -ForegroundColor Green
    Write-Host ("  trace_id=" + $convTurn.id)
    Write-Host ("  view it at: $host_/project/-/traces/" + $convTurn.id)
    exit 0
} else {
    Write-Host ("FAIL: no trace on cloud carries session_id=" + $convId) -ForegroundColor Red
    Write-Host "Sessions API cross-check:"
    try {
        $sessResp = Invoke-RestMethod -Uri "$host_/api/public/sessions?limit=5" -Headers $headers -Method GET -TimeoutSec 15
        Write-Host ("  sessions total=" + $sessResp.meta.totalItems)
        $sessResp.data | Select-Object -First 5 id, createdAt | Format-Table -AutoSize
    } catch {
        Write-Host ("  sessions query ERR: " + $_.Exception.Message)
    }
    exit 1
}
