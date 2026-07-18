"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAuth } from "@/components/AuthProvider";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/incidents", label: "Incidents" },
  { href: "/knowledge", label: "Knowledge" },
  { href: "/integrations", label: "Integrations" },
  { href: "/settings", label: "Settings" },
] as const;

export default function WorkspaceShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { signOut } = useAuth();

  return (
    <div className="workspace">
      <aside className="workspace-nav">
        <div className="workspace-brand">
          <Link href="/dashboard" className="brand-link">
            breadcrumbs
          </Link>
        </div>
        <nav className="workspace-links" aria-label="Main">
          {NAV_ITEMS.map((item) => {
            const active =
              pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={active ? "nav-link nav-link-active" : "nav-link"}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        <button type="button" className="btn btn-ghost" onClick={() => signOut()}>
          Log out
        </button>
      </aside>
      <div className="workspace-main">{children}</div>
    </div>
  );
}
