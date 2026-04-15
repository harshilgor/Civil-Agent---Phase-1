import { useEditStore } from "@/state/editStore";

export function UndoRedo() {
  const undo = useEditStore((s) => s.undo);
  const redo = useEditStore((s) => s.redo);
  return (
    <span>
      <button type="button" onClick={undo}>
        Undo
      </button>
      <button type="button" onClick={redo}>
        Redo
      </button>
    </span>
  );
}
