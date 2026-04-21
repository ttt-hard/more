import { create } from "zustand";

import type { DocumentViewMode, UtilityDrawerTab } from "../components/more/types";

type AgentPhaseStatus = {
  phase: "planning" | "tool" | "answering";
  label: string;
  detail?: string;
};

const DEFAULT_AGENT_DOCK_WIDTH = 352;
const MIN_AGENT_DOCK_WIDTH = 320;
const MAX_AGENT_DOCK_WIDTH = 420;

function clampDockWidth(value: number): number {
  return Math.min(MAX_AGENT_DOCK_WIDTH, Math.max(MIN_AGENT_DOCK_WIDTH, value));
}

function readAgentDockWidth(): number {
  if (typeof window === "undefined") {
    return DEFAULT_AGENT_DOCK_WIDTH;
  }

  const raw = window.localStorage.getItem("more.agentDockWidth");
  const parsed = raw ? Number.parseInt(raw, 10) : NaN;
  return Number.isFinite(parsed) ? clampDockWidth(parsed) : DEFAULT_AGENT_DOCK_WIDTH;
}

type UiState = {
  documentViewMode: DocumentViewMode;
  isAgentDockCollapsed: boolean;
  isUtilityDrawerOpen: boolean;
  utilityDrawerTab: UtilityDrawerTab;
  sidebarCollapsed: boolean;
  agentDockWidth: number;
  agentDockResizing: boolean;
  agentPhaseStatus: AgentPhaseStatus | null;
  activeTag: string | null;
  draftMap: Record<string, string>;
  setDocumentViewMode: (value: DocumentViewMode) => void;
  setAgentDockCollapsed: (value: boolean) => void;
  toggleAgentDockCollapsed: () => void;
  setAgentDockWidth: (value: number, options?: { persist?: boolean }) => void;
  setAgentDockResizing: (value: boolean) => void;
  setAgentPhaseStatus: (value: AgentPhaseStatus | null) => void;
  setUtilityDrawerOpen: (value: boolean) => void;
  setUtilityDrawerTab: (value: UtilityDrawerTab) => void;
  setSidebarCollapsed: (value: boolean) => void;
  toggleSidebarCollapsed: () => void;
  setActiveTag: (value: string | null) => void;
  setDraftContent: (key: string, value: string) => void;
};

export const useUiStore = create<UiState>((set) => ({
  documentViewMode: "source",
  isAgentDockCollapsed: false,
  isUtilityDrawerOpen: false,
  utilityDrawerTab: "import",
  sidebarCollapsed: false,
  agentDockWidth: readAgentDockWidth(),
  agentDockResizing: false,
  agentPhaseStatus: null,
  activeTag: null,
  draftMap: {},
  setDocumentViewMode: (value) =>
    set((state) => (state.documentViewMode === value ? state : { documentViewMode: value })),
  setAgentDockCollapsed: (value) =>
    set((state) => (state.isAgentDockCollapsed === value ? state : { isAgentDockCollapsed: value })),
  toggleAgentDockCollapsed: () =>
    set((state) => ({ isAgentDockCollapsed: !state.isAgentDockCollapsed })),
  setAgentDockWidth: (value, options) => {
    const next = clampDockWidth(value);
    const current = useUiStore.getState().agentDockWidth;
    if (current === next) {
      return;
    }
    if (options?.persist !== false && typeof window !== "undefined") {
      window.localStorage.setItem("more.agentDockWidth", String(next));
    }
    set({ agentDockWidth: next });
  },
  setAgentDockResizing: (value) =>
    set((state) => (state.agentDockResizing === value ? state : { agentDockResizing: value })),
  setAgentPhaseStatus: (value) =>
    set((state) => {
      const current = state.agentPhaseStatus;
      if (
        current === value ||
        (current &&
          value &&
          current.phase === value.phase &&
          current.label === value.label &&
          current.detail === value.detail) ||
        (!current && !value)
      ) {
        return state;
      }
      return { agentPhaseStatus: value };
    }),
  setUtilityDrawerOpen: (value) =>
    set((state) => (state.isUtilityDrawerOpen === value ? state : { isUtilityDrawerOpen: value })),
  setUtilityDrawerTab: (value) =>
    set((state) => (state.utilityDrawerTab === value ? state : { utilityDrawerTab: value })),
  setSidebarCollapsed: (value) =>
    set((state) => (state.sidebarCollapsed === value ? state : { sidebarCollapsed: value })),
  toggleSidebarCollapsed: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
  setActiveTag: (value) => set((state) => (state.activeTag === value ? state : { activeTag: value })),
  setDraftContent: (key, value) =>
    set((state) => {
      if (state.draftMap[key] === value) {
        return state;
      }
      return {
        draftMap: {
          ...state.draftMap,
          [key]: value,
        },
      };
    }),
}));
