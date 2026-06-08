import { useState, useCallback, useEffect, useRef } from 'react';

export interface UseApiQueryResult<T> {
  data: T | undefined;
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
  refetch: () => Promise<T>;
}

export function useApiQuery<T>(key: string, fetcher: () => Promise<T>): UseApiQueryResult<T> {
  const [data, setData] = useState<T | undefined>(undefined);
  const [isLoading, setIsLoading] = useState(true);
  const [isError, setIsError] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const mountedRef = useRef(true);
  const requestIdRef = useRef(0);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const execute = useCallback(async (): Promise<T> => {
    const requestId = ++requestIdRef.current;
    setIsLoading(true);
    setIsError(false);
    setError(null);
    try {
      const result = await fetcherRef.current();
      if (mountedRef.current && requestId === requestIdRef.current) {
        setData(result);
      }
      return result;
    } catch (err: any) {
      const e = err instanceof Error ? err : new Error(String(err));
      console.error(`[useApiQuery ${key}]`, e);
      if (mountedRef.current && requestId === requestIdRef.current) {
        setIsError(true);
        setError(e);
      }
      throw e;
    } finally {
      if (mountedRef.current && requestId === requestIdRef.current) {
        setIsLoading(false);
      }
    }
  }, [key]);

  useEffect(() => {
    execute();
  }, [execute]);

  const refetch = useCallback(() => {
    return execute();
  }, [execute]);

  return { data, isLoading, isError, error, refetch };
}

export interface UseApiMutationResult<TInput, TOutput> {
  mutateAsync: (input: TInput) => Promise<TOutput>;
  isPending: boolean;
  error: Error | null;
}

export function useApiMutation<TInput, TOutput>(
  mutator: (input: TInput) => Promise<TOutput>
): UseApiMutationResult<TInput, TOutput> {
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const mutatorRef = useRef(mutator);
  mutatorRef.current = mutator;

  const mutateAsync = useCallback(async (input: TInput): Promise<TOutput> => {
    setIsPending(true);
    setError(null);
    try {
      const result = await mutatorRef.current(input);
      return result;
    } catch (err: any) {
      const e = err instanceof Error ? err : new Error(String(err));
      console.error('[useApiMutation]', e);
      setError(e);
      throw e;
    } finally {
      setIsPending(false);
    }
  }, []);

  return { mutateAsync, isPending, error };
}
