import { createContext, useContext, useEffect, useRef, useState, useCallback, type ReactNode } from "react";

// SSE イベントタイプ
export const SSE_EVENT_CONTENT = "content";

export type SSEEventType = typeof SSE_EVENT_CONTENT;

type SSEListener = (eventType: SSEEventType) => void;

interface SSEContextValue {
    isConnected: boolean;
    subscribe: (listener: SSEListener) => () => void;
}

const SSEContext = createContext<SSEContextValue | null>(null);

interface SSEProviderProps {
    children: ReactNode;
}

export function SSEProvider({ children }: SSEProviderProps) {
    const [isConnected, setIsConnected] = useState(false);
    const eventSourceRef = useRef<EventSource | null>(null);
    const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const listenersRef = useRef<Set<SSEListener>>(new Set());

    const notifyListeners = useCallback((eventType: SSEEventType) => {
        listenersRef.current.forEach((listener) => {
            try {
                listener(eventType);
            } catch (error) {
                console.error("SSE listener error:", error);
            }
        });
    }, []);

    useEffect(() => {
        const connectSSE = () => {
            if (eventSourceRef.current) {
                eventSourceRef.current.close();
            }

            const eventSource = new EventSource("/price/api/event");

            eventSource.onopen = () => {
                setIsConnected(true);
            };

            eventSource.onmessage = (event) => {
                if (event.data === SSE_EVENT_CONTENT) {
                    notifyListeners(SSE_EVENT_CONTENT);
                }
            };

            eventSource.onerror = () => {
                setIsConnected(false);
                eventSource.close();
                // 5秒後に再接続
                reconnectTimerRef.current = setTimeout(() => {
                    connectSSE();
                }, 5000);
            };

            eventSourceRef.current = eventSource;
        };

        connectSSE();

        return () => {
            if (eventSourceRef.current) {
                eventSourceRef.current.close();
            }
            if (reconnectTimerRef.current) {
                clearTimeout(reconnectTimerRef.current);
            }
        };
    }, [notifyListeners]);

    const subscribe = useCallback((listener: SSEListener) => {
        listenersRef.current.add(listener);
        return () => {
            listenersRef.current.delete(listener);
        };
    }, []);

    return (
        <SSEContext.Provider value={{ isConnected, subscribe }}>
            {children}
        </SSEContext.Provider>
    );
}

export function useSSE(): SSEContextValue {
    const context = useContext(SSEContext);
    if (!context) {
        throw new Error("useSSE must be used within an SSEProvider");
    }
    return context;
}

// SSEイベントを購読するためのフック
export function useSSESubscription(callback: () => void) {
    const { subscribe } = useSSE();

    useEffect(() => {
        const unsubscribe = subscribe(() => {
            callback();
        });
        return unsubscribe;
    }, [subscribe, callback]);
}
