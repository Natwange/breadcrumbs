"use client";

import { useState } from "react";

import { useAuth } from "@/components/AuthProvider";

type Mode = "login" | "signup";

export default function AuthForm() {
  const { signIn, signUp, configured } = useAuth();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    setSubmitting(true);

    const action = mode === "login" ? signIn : signUp;
    const { error: actionError } = await action(email, password);

    setSubmitting(false);

    if (actionError) {
      setError(actionError);
      return;
    }

    if (mode === "signup") {
      setMessage(
        "Account created. If email confirmation is enabled, check your inbox before signing in."
      );
    }
  }

  if (!configured) {
    return (
      <div className="health-card">
        <div className="health-header">
          <span className="health-dot" style={{ backgroundColor: "#ef4444" }} />
          <span className="health-title">Supabase not configured</span>
        </div>
        <p className="health-detail">
          Set <code>NEXT_PUBLIC_SUPABASE_URL</code> and{" "}
          <code>NEXT_PUBLIC_SUPABASE_ANON_KEY</code> in{" "}
          <code>frontend/.env.local</code>, then restart the dev server.
        </p>
      </div>
    );
  }

  return (
    <div className="health-card">
      <div className="auth-tabs">
        <button
          type="button"
          className={`auth-tab ${mode === "login" ? "auth-tab-active" : ""}`}
          onClick={() => setMode("login")}
        >
          Log in
        </button>
        <button
          type="button"
          className={`auth-tab ${mode === "signup" ? "auth-tab-active" : ""}`}
          onClick={() => setMode("signup")}
        >
          Sign up
        </button>
      </div>

      <form className="auth-form" onSubmit={handleSubmit}>
        <label className="auth-label">
          Email
          <input
            className="auth-input"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label className="auth-label">
          Password
          <input
            className="auth-input"
            type="password"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            required
            minLength={6}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>

        {error && <p className="auth-error">{error}</p>}
        {message && <p className="auth-message">{message}</p>}

        <button type="submit" className="health-button" disabled={submitting}>
          {submitting
            ? "Please wait…"
            : mode === "login"
              ? "Log in"
              : "Create account"}
        </button>
      </form>
    </div>
  );
}
