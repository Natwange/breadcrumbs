"use client";

import { useEffect, useState } from "react";

import {
  EmptyState,
  ErrorBanner,
  LoadingCard,
  PageHeader,
  StatusBadge,
} from "@/components/ui/Primitives";
import {
  fetchCurrentUser,
  getOrganizationSettings,
  listOrganizationMembers,
  type CurrentUser,
  type OrganizationMember,
  type OrganizationSettings,
} from "@/lib/api";

export default function SettingsPage() {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [settings, setSettings] = useState<OrganizationSettings | null>(null);
  const [members, setMembers] = useState<OrganizationMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const [me, orgSettings, orgMembers] = await Promise.all([
          fetchCurrentUser(),
          getOrganizationSettings(),
          listOrganizationMembers(),
        ]);
        if (!active) return;
        setUser(me);
        setSettings(orgSettings);
        setMembers(orgMembers);
      } catch (err) {
        if (!active) return;
        setError(err instanceof Error ? err.message : "Failed to load settings");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  if (loading) return <LoadingCard />;
  if (error) return <ErrorBanner message={error} />;

  return (
    <div className="workspace-content">
      <PageHeader
        title="Settings"
        description="Organization profile and membership."
      />

      <section className="section">
        <h2 className="section-title">Account</h2>
        {user ? (
          <div className="card stack">
            <p>
              <strong>{user.full_name ?? user.email}</strong>
            </p>
            <p className="muted">{user.email}</p>
            <p className="muted small">
              Organization: {user.organization.name} ({user.organization.slug})
            </p>
          </div>
        ) : (
          <EmptyState title="No user profile" />
        )}
      </section>

      <section className="section">
        <h2 className="section-title">Organization settings</h2>
        {settings ? (
          <div className="card stack">
            <p>Timezone: {settings.timezone}</p>
            <p>Default severity: {settings.default_severity ?? "—"}</p>
            {settings.notes && <p className="pre-wrap">{settings.notes}</p>}
          </div>
        ) : (
          <EmptyState title="No settings record" />
        )}
      </section>

      <section className="section">
        <h2 className="section-title">Members</h2>
        {members.length === 0 ? (
          <EmptyState title="No members" />
        ) : (
          <ul className="data-list">
            {members.map((member) => (
              <li key={member.id} className="card">
                <div className="card-row">
                  <span className="muted small">{member.user_id}</span>
                  <StatusBadge status={member.status} />
                </div>
                <p>
                  Role: <strong>{member.role}</strong>
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
