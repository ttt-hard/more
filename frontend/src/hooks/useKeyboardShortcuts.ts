import { useEffect } from "react";

import { agentConversationStore } from "@/hooks/useAgentConversation";
import { useWorkspaceStore } from "@/stores/workspaceStore";

const SEARCH_INPUT_ID = "more-search-input";

/**
 * Global keyboard shortcut dispatcher. Mounted once at the App root.
 * Mirrors VSCode / Notion conventions where practical:
 *   Ctrl/Cmd+F  → focus search input
 *   Ctrl/Cmd+N  → new blank note in the default folder
 *   Ctrl/Cmd+W  → close the active tab
 *   Ctrl/Cmd+S  → force save the current document (autosave also runs)
 *   Ctrl/Cmd+Shift+N → new AI conversation
 *   Ctrl/Cmd+K  → focus the prompt textarea (ready to chat)
 *
 * Shortcuts are ignored while the user is actively typing inside an input/
 * textarea (unless the shortcut is well-established like Ctrl+S).
 */
export function useKeyboardShortcuts(): void {
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const mod = event.ctrlKey || event.metaKey;
      if (!mod && event.key !== "Escape") {
        return;
      }
      const target = event.target as HTMLElement | null;
      const isEditableTarget =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        (target instanceof HTMLElement && target.isContentEditable);

      const key = event.key.toLowerCase();

      // Ctrl/Cmd + F — focus workspace search.
      if (mod && !event.shiftKey && key === "f") {
        event.preventDefault();
        const input = document.getElementById(SEARCH_INPUT_ID) as HTMLInputElement | null;
        if (input) {
          input.focus();
          input.select();
        }
        return;
      }

      // Ctrl/Cmd + Shift + N — new AI conversation.
      if (mod && event.shiftKey && key === "n") {
        event.preventDefault();
        void agentConversationStore.getState().createNewConversation();
        return;
      }

      // Ctrl/Cmd + N — new blank note. Ignore when typing into a text field.
      if (mod && !event.shiftKey && key === "n") {
        if (isEditableTarget) {
          return;
        }
        event.preventDefault();
        void useWorkspaceStore.getState().createDraftNote();
        return;
      }

      // Ctrl/Cmd + W — close active tab. Never hijack when typing.
      if (mod && !event.shiftKey && key === "w") {
        if (isEditableTarget) {
          return;
        }
        const store = useWorkspaceStore.getState();
        const path = store.selectedPath;
        if (path) {
          event.preventDefault();
          store.closeTab(path);
        }
        return;
      }

      // Ctrl/Cmd + S — save. Always intercept so browser doesn't open save-page.
      if (mod && !event.shiftKey && key === "s") {
        event.preventDefault();
        void useWorkspaceStore.getState().saveSelectedDocument();
        return;
      }

      // Ctrl/Cmd + K — focus the prompt composer textarea.
      if (mod && !event.shiftKey && key === "k") {
        event.preventDefault();
        const composer = document.querySelector<HTMLTextAreaElement>(".dock-prompt");
        composer?.focus();
        return;
      }

      // Escape — blur the currently focused input-like element.
      if (event.key === "Escape" && isEditableTarget) {
        (target as HTMLElement).blur();
      }
    };

    window.addEventListener("keydown", handler);
    return () => {
      window.removeEventListener("keydown", handler);
    };
  }, []);
}

export const SEARCH_INPUT_DOM_ID = SEARCH_INPUT_ID;
