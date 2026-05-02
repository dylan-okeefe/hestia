import { useCallback, useRef, useState } from 'react';

export interface UndoRedoState<T> {
  push: () => void;
  undo: () => T | undefined;
  redo: () => T | undefined;
  canUndo: boolean;
  canRedo: boolean;
}

export function useUndoRedo<T>(getCurrent: () => T): UndoRedoState<T> {
  const [past, setPast] = useState<T[]>([]);
  const [future, setFuture] = useState<T[]>([]);
  const pastRef = useRef<T[]>([]);
  const futureRef = useRef<T[]>([]);

  pastRef.current = past;
  futureRef.current = future;

  const push = useCallback(() => {
    const current = getCurrent();
    setPast((p) => [...p.slice(-49), current]);
    setFuture([]);
  }, [getCurrent]);

  const undo = useCallback((): T | undefined => {
    const current = getCurrent();
    const p = pastRef.current;
    const previous = p[p.length - 1];
    if (!previous) return undefined;
    setPast(p.slice(0, -1));
    setFuture((f) => [current, ...f]);
    return previous;
  }, [getCurrent]);

  const redo = useCallback((): T | undefined => {
    const current = getCurrent();
    const f = futureRef.current;
    const next = f[0];
    if (!next) return undefined;
    setFuture(f.slice(1));
    setPast((p) => [...p, current]);
    return next;
  }, [getCurrent]);

  return {
    push,
    undo,
    redo,
    canUndo: past.length > 0,
    canRedo: future.length > 0,
  };
}
