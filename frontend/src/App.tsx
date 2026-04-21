import { useEffect, useRef } from "react";

import { AgentDock } from "./components/more/AgentDock";
import { DocumentHub } from "./components/more/DocumentHub";
import { Sidebar } from "./components/more/Sidebar";
import { TopBar } from "./components/more/TopBar";
import { UtilityDrawer } from "./components/more/UtilityDrawer";
import { agentConversationStore } from "./hooks/useAgentConversation";
import { useKeyboardShortcuts } from "./hooks/useKeyboardShortcuts";
import { useUiStore } from "./stores/uiStore";
import { useWorkspaceStore } from "./stores/workspaceStore";

export default function App() {
  useKeyboardShortcuts();
  const sidebarCollapsed = useUiStore((state) => state.sidebarCollapsed);
  const isAgentDockCollapsed = useUiStore((state) => state.isAgentDockCollapsed);
  const agentDockWidth = useUiStore((state) => state.agentDockWidth);
  const agentDockResizing = useUiStore((state) => state.agentDockResizing);
  const workspaceError = useWorkspaceStore((state) => state.error);

  // Restore the previously-active workspace + open tabs once per page load.
  // StrictMode double-invokes effects in dev, so we guard with a ref so we only
  // fire the async bootstrap once. The store itself also bails out if a
  // workspace is already active.
  const bootstrappedRef = useRef(false);
  useEffect(() => {
    if (bootstrappedRef.current) return;
    bootstrappedRef.current = true;
    const run = async () => {
      await useWorkspaceStore.getState().bootstrapSession();
      const workspace = useWorkspaceStore.getState().workspace;
      if (workspace) {
        await agentConversationStore.getState().resetForWorkspace(workspace);
      }
    };
    void run();
  }, []);

  return (
    <div className="app-stage">
      <div
        className={`workspace-frame ${agentDockResizing ? "workspace-frame-resizing" : ""}`}
        style={{
          gridTemplateColumns: `${sidebarCollapsed ? "72px" : "228px"} minmax(0, 1fr) ${
            isAgentDockCollapsed ? "68px" : `${agentDockWidth}px`
          }`,
        }}
      >
        <Sidebar />

        <div className="main-shell">
          <TopBar />
          {workspaceError ? <div className="error-banner">{workspaceError}</div> : null}
          <div className="main-content-shell">
            <DocumentHub />
          </div>
        </div>

        <AgentDock />
      </div>

      <UtilityDrawer />
    </div>
  );
}
