/**
 * Clinical Warmth system layer: keep live notifications calm, predictable and
 * battery-conscious while preserving Emma's coral attention signal.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  getMyNotifications,
  getReplacementOffers,
  markNotificationRead,
  respondReplacementOffer,
  type ReplacementOffer,
  type StaffNotification,
} from "@/lib/api";
import { useAuth } from "./AuthContext";

const ACTIVE_POLL_MS = 30_000;
const MAX_BACKOFF_MS = 5 * 60_000;

type ConnectionState = "idle" | "syncing" | "live" | "offline" | "degraded";

interface AttentionContextValue {
  notifications: StaffNotification[];
  offers: ReplacementOffer[];
  unreadCount: number;
  pendingOfferCount: number;
  attentionCount: number;
  latestNotification: StaffNotification | null;
  loading: boolean;
  error: string;
  connectionState: ConnectionState;
  lastUpdatedAt: string | null;
  refresh: () => Promise<boolean>;
  markRead: (notification: StaffNotification) => Promise<void>;
  respondToOffer: (offer: ReplacementOffer, accept: boolean, note?: string) => Promise<void>;
}

const AttentionContext = createContext<AttentionContextValue | null>(null);

export function AttentionProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  const [notifications, setNotifications] = useState<StaffNotification[]>([]);
  const [offers, setOffers] = useState<ReplacementOffer[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [connectionState, setConnectionState] = useState<ConnectionState>("idle");
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);
  const inFlightRef = useRef<Promise<boolean> | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const offerStatusRef = useRef<Map<string, string>>(new Map());
  const notificationRef = useRef<Set<string>>(new Set());

  const refresh = useCallback(async () => {
    if (!isAuthenticated) return false;
    if (inFlightRef.current) return inFlightRef.current;
    if (!navigator.onLine) {
      setConnectionState("offline");
      setError("目前離線；重新連線後會自動更新通知");
      return false;
    }

    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setConnectionState("syncing");

    const operation = Promise.allSettled([
      getMyNotifications(false, controller.signal),
      getReplacementOffers(undefined, controller.signal),
    ])
      .then((results) => {
        let dataInvalidated = false;
        if (results[0].status === "fulfilled") {
          const next = results[0].value;
          if (notificationRef.current.size > 0 && next.some((item) =>
            !notificationRef.current.has(item.id) &&
            ["leave_request", "roster_version", "replacement_offer"].includes(item.related_type || ""),
          )) dataInvalidated = true;
          notificationRef.current = new Set(next.map((item) => item.id));
          setNotifications(next);
        }
        if (results[1].status === "fulfilled") {
          const next = results[1].value;
          if (offerStatusRef.current.size > 0 && next.some((offer) => {
            const previous = offerStatusRef.current.get(offer.id);
            return previous && previous !== offer.status && ["approved", "superseded"].includes(offer.status);
          })) dataInvalidated = true;
          offerStatusRef.current = new Map(next.map((offer) => [offer.id, offer.status]));
          setOffers(next);
        }

        if (dataInvalidated) {
          window.dispatchEvent(new CustomEvent("emma:staff-data-invalidated"));
        }

        const successCount = results.filter((result) => result.status === "fulfilled").length;
        if (successCount === 2) {
          setError("");
          setConnectionState("live");
          setLastUpdatedAt(new Date().toISOString());
          return true;
        }

        if (successCount === 1) {
          setError("部分通知暫時未能更新；已保留上一個有效狀態");
          setConnectionState("degraded");
          setLastUpdatedAt(new Date().toISOString());
          return false;
        }

        setError("未能更新通知；系統會稍後自動重試");
        setConnectionState("degraded");
        return false;
      })
      .catch((err) => {
        if (err instanceof DOMException && err.name === "AbortError") return false;
        setError("未能更新通知；系統會稍後自動重試");
        setConnectionState("degraded");
        return false;
      })
      .finally(() => {
        if (abortRef.current === controller) abortRef.current = null;
        inFlightRef.current = null;
        setLoading(false);
      });

    inFlightRef.current = operation;
    return operation;
  }, [isAuthenticated]);

  useEffect(() => {
    if (!isAuthenticated) {
      abortRef.current?.abort();
      setNotifications([]);
      setOffers([]);
      setLoading(false);
      setError("");
      setConnectionState("idle");
      setLastUpdatedAt(null);
      offerStatusRef.current = new Map();
      notificationRef.current = new Set();
      return;
    }

    let stopped = false;
    let timer: number | null = null;
    let failures = 0;

    const schedule = (delay: number) => {
      if (timer !== null) window.clearTimeout(timer);
      if (!stopped) timer = window.setTimeout(tick, delay);
    };

    const tick = async () => {
      if (stopped) return;
      if (document.visibilityState !== "visible") {
        schedule(ACTIVE_POLL_MS);
        return;
      }
      if (!navigator.onLine) {
        setConnectionState("offline");
        schedule(ACTIVE_POLL_MS);
        return;
      }

      const ok = await refresh();
      failures = ok ? 0 : Math.min(failures + 1, 4);
      const delay = ok
        ? ACTIVE_POLL_MS
        : Math.min(ACTIVE_POLL_MS * 2 ** failures, MAX_BACKOFF_MS);
      schedule(delay);
    };

    const resume = () => {
      if (timer !== null) window.clearTimeout(timer);
      if (document.visibilityState === "visible" && navigator.onLine) void tick();
    };
    const goOffline = () => {
      setConnectionState("offline");
      setError("目前離線；重新連線後會自動更新通知");
      schedule(ACTIVE_POLL_MS);
    };

    document.addEventListener("visibilitychange", resume);
    window.addEventListener("online", resume);
    window.addEventListener("offline", goOffline);
    window.addEventListener("focus", resume);
    void tick();

    return () => {
      stopped = true;
      if (timer !== null) window.clearTimeout(timer);
      abortRef.current?.abort();
      document.removeEventListener("visibilitychange", resume);
      window.removeEventListener("online", resume);
      window.removeEventListener("offline", goOffline);
      window.removeEventListener("focus", resume);
    };
  }, [isAuthenticated, refresh]);

  const markRead = useCallback(async (notification: StaffNotification) => {
    if (notification.status === "read" || notification.read_at) return;
    await markNotificationRead(notification.id);
    setNotifications((current) =>
      current.map((item) =>
        item.id === notification.id
          ? { ...item, status: "read", read_at: new Date().toISOString() }
          : item,
      ),
    );
  }, []);

  const respondToOffer = useCallback(
    async (offer: ReplacementOffer, accept: boolean, note?: string) => {
      const updated = await respondReplacementOffer(offer.id, accept, note);
      setOffers((current) => current.map((item) => (item.id === offer.id ? updated : item)));
      await refresh();
    },
    [refresh],
  );

  const value = useMemo<AttentionContextValue>(() => {
    const unreadCount = notifications.filter(
      (notification) => notification.status !== "read" && !notification.read_at,
    ).length;
    const pendingOfferCount = offers.filter((offer) => offer.status === "pending").length;
    const latestNotification = [...notifications].sort((a, b) =>
      b.created_at.localeCompare(a.created_at),
    )[0] || null;

    return {
      notifications,
      offers,
      unreadCount,
      pendingOfferCount,
      attentionCount: unreadCount + pendingOfferCount,
      latestNotification,
      loading,
      error,
      connectionState,
      lastUpdatedAt,
      refresh,
      markRead,
      respondToOffer,
    };
  }, [notifications, offers, loading, error, connectionState, lastUpdatedAt, refresh, markRead, respondToOffer]);

  return <AttentionContext.Provider value={value}>{children}</AttentionContext.Provider>;
}

export function useAttention() {
  const value = useContext(AttentionContext);
  if (!value) throw new Error("useAttention must be used within AttentionProvider");
  return value;
}
