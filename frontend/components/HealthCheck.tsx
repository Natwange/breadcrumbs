"use client";

import { useCallback, useEffect, useState } from "react";

import { API_BASE_URL, fetchHealth } from "@/lib/api";

type Status = "loading" | "ok" | "error";

export default function HealthCheck() {
  const [status, setStatus] = useState<Status>("loading");
  const [detail, setDetail] = useState<string>("Checking backend…");

  const check = useCallback(async (signal?: AbortSignal) => {
    setStatus("loading");
    setDetail("Checking backend…");
    try {
      const data = await fetchHealth(signal);
      setStatus("ok");
      setDetail(`Backend status: ${data.status}`);
    } catch (error) {
      if (signal?.aborted) return;
      setStatus("error");
      setDetail(
        error instanceof Error
          ? `Backend unreachable: ${error.message}`
          : "Backend unreachable"
      );
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    check(controller.signal);
    return () => controller.abort();
  }, [check]);

  const indicatorColor =
    status === "ok" ? "#22c55e" : status === "error" ? "#ef4444" : "#eab308";

  return (
    <div className="health-card">
      <div className="health-header">
        <span
          className="health-dot"
          style={{ backgroundColor: indicatorColor }}
          aria-hidden="true"
        />
        <span className="health-title">Backend health</span>
      </div>
      <p className="health-detail">{detail}</p>
      <p className="health-endpoint">
        <code>{`${API_BASE_URL}/health`}</code>
      </p>
      <button
        type="button"
        className="health-button"
        onClick={() => check()}
        disabled={status === "loading"}
      >
        {status === "loading" ? "Checking…" : "Re-check"}
      </button>
    </div>
  );
}
