import { NavLink, Outlet } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import {
  LayoutDashboard,
  Bot,
  Building2,
  ShieldAlert,
  ClipboardList,
  Network,
  FileText,
  Activity,
  Inbox,
  Settings as SettingsIcon,
  Power,
} from "lucide-react";
import { useApi } from "../lib/api";
import { Badge } from "./ui";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/agents", label: "Agents", icon: Bot },
  { to: "/vendors", label: "Vendors", icon: Building2 },
  { to: "/findings", label: "Findings", icon: ShieldAlert },
  { to: "/questionnaires", label: "Questionnaires", icon: ClipboardList },
  { to: "/concentration", label: "Concentration Risks", icon: Network },
  { to: "/digest", label: "Executive Digest", icon: FileText },
  { to: "/traces", label: "Traces", icon: Activity },
  { to: "/dlq", label: "DLQ", icon: Inbox },
];

export default function Layout() {
  const api = useApi();

  const health = useQuery({
    queryKey: ["fleet-health"],
    queryFn: () => api.getFleetHealth(),
    refetchInterval: 15000,
    retry: false,
  });

  const connectionOk = health.isSuccess;
  const autonomy = health.data?.global_autonomy_level;

  const autonomyTone =
    autonomy === undefined ? "gray" : autonomy === 0 ? "red" : autonomy === 3 ? "green" : "amber";
  const autonomyLabel =
    autonomy === undefined
      ? "—"
      : ["L0 Observe", "L1 Draft", "L2 Approve", "L3 Autonomous"][autonomy] ?? `L${autonomy}`;

  return (
    <div className="flex h-screen w-full overflow-hidden bg-zinc-950 text-zinc-100">
      <aside className="flex w-60 shrink-0 flex-col border-r border-zinc-800 bg-zinc-950/80">
        <div className="flex items-center gap-2 border-b border-zinc-800 px-4 py-4">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-sm font-bold text-white">
            B
          </div>
          <div>
            <div className="text-sm font-semibold leading-tight text-zinc-100">BULWARK</div>
            <div className="text-[11px] leading-tight text-zinc-500">Assurance Fleet</div>
          </div>
        </div>

        <nav className="flex-1 space-y-0.5 overflow-y-auto px-2 py-3">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                clsx(
                  "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-indigo-600/15 text-indigo-300"
                    : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-100",
                )
              }
            >
              <Icon className="h-4 w-4 shrink-0" />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-zinc-800 px-2 py-3">
          <NavLink
            to="/settings"
            className={({ isActive }) =>
              clsx(
                "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-indigo-600/15 text-indigo-300"
                  : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-100",
              )
            }
          >
            <SettingsIcon className="h-4 w-4 shrink-0" />
            Connection
          </NavLink>
        </div>
      </aside>

      <div className="flex flex-1 flex-col overflow-hidden">
        <header className="flex shrink-0 items-center justify-between border-b border-zinc-800 bg-zinc-950/60 px-6 py-3">
          <div className="flex items-center gap-2 text-xs text-zinc-500">
            <span
              className={clsx(
                "inline-block h-2 w-2 rounded-full",
                connectionOk ? "bg-emerald-500" : "bg-rose-500",
              )}
            />
            {connectionOk ? "Connected to Agent Gateway" : "Not connected — check Connection settings"}
          </div>
          <div className="flex items-center gap-3">
            <Badge tone={autonomyTone as "gray" | "red" | "amber" | "green"}>
              <Power className="h-3 w-3" />
              {autonomyLabel}
            </Badge>
            {health.data && health.data.dlq_depth > 0 && (
              <Badge tone="amber">{health.data.dlq_depth} in DLQ</Badge>
            )}
          </div>
        </header>

        <main className="flex-1 overflow-y-auto px-6 py-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
