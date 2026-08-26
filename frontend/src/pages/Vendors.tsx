import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApi, ApiError } from "../lib/api";
import { useSort } from "../lib/sort";
import type { Vendor } from "../lib/types";
import {
  Card,
  Table,
  Th,
  Td,
  Tr,
  Badge,
  Button,
  Input,
  Select,
  Textarea,
  LoadingBlock,
  ErrorBlock,
  EmptyBlock,
  toneForTier,
} from "../components/ui";
import { Plus, Upload } from "lucide-react";

const DOC_TYPES = ["SOC2", "ISO", "pen-test", "DPA", "MSA", "contract", "SLA", "order form"];
const TIERS = ["critical", "high", "moderate", "low"];

export default function Vendors() {
  const api = useApi();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [tierFilter, setTierFilter] = useState("");
  const [showRegister, setShowRegister] = useState(false);
  const [showSubmit, setShowSubmit] = useState(false);
  const sort = useSort<Vendor>();

  const vendors = useQuery({ queryKey: ["vendors"], queryFn: () => api.listVendors() });

  const [regName, setRegName] = useState("");
  const [regTier, setRegTier] = useState("moderate");
  const registerMutation = useMutation({
    mutationFn: () => api.registerVendor({ name: regName, tier: regTier }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["vendors"] });
      setRegName("");
      setShowRegister(false);
    },
  });

  const [subVendor, setSubVendor] = useState("");
  const [subDocType, setSubDocType] = useState(DOC_TYPES[0]);
  const [subText, setSubText] = useState("");
  const submitMutation = useMutation({
    mutationFn: () =>
      api.submitArtifact({ vendor_name: subVendor, doc_type: subDocType, raw_text: subText }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["vendors"] });
      setSubVendor("");
      setSubText("");
      setShowSubmit(false);
    },
  });

  if (vendors.isLoading) return <LoadingBlock label="Loading vendors…" />;
  if (vendors.isError) return <ErrorBlock message={(vendors.error as Error).message} />;

  const filtered = sort.apply(
    vendors.data!.filter(
      (v) => v.name.toLowerCase().includes(search.toLowerCase()) && (!tierFilter || v.tier === tierFilter),
    ),
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-zinc-100">Vendors</h1>
          <p className="mt-1 text-sm text-zinc-500">
            {vendors.data!.length} vendor{vendors.data!.length === 1 ? "" : "s"} — blind_window_days
            computed live.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" onClick={() => setShowRegister((s) => !s)}>
            <Plus className="h-3.5 w-3.5" /> Register vendor
          </Button>
          <Button variant="primary" onClick={() => setShowSubmit((s) => !s)}>
            <Upload className="h-3.5 w-3.5" /> Submit artifact
          </Button>
        </div>
      </div>

      {showRegister && (
        <Card title="Register a vendor" subtitle="POST /vendors — sets tier ahead of any artifact arriving">
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label className="mb-1 block text-xs text-zinc-500">Name</label>
              <Input value={regName} onChange={setRegName} placeholder="Critical Payments Co" />
            </div>
            <div>
              <label className="mb-1 block text-xs text-zinc-500">Tier</label>
              <Select
                value={regTier}
                onChange={setRegTier}
                options={["critical", "high", "moderate", "low"].map((t) => ({ value: t, label: t }))}
              />
            </div>
            <Button
              variant="primary"
              disabled={!regName || registerMutation.isPending}
              onClick={() => registerMutation.mutate()}
            >
              {registerMutation.isPending ? "Registering…" : "Register"}
            </Button>
          </div>
          {registerMutation.isError && (
            <div className="mt-3">
              <ErrorBlock message={(registerMutation.error as ApiError).message} />
            </div>
          )}
        </Card>
      )}

      {showSubmit && (
        <Card
          title="Submit an artifact"
          subtitle="POST /vendors/artifacts — screened by Model Armor before any LLM call; requires Gemini credentials to run the full Onboard/Assure loop"
        >
          <div className="space-y-3">
            <div className="flex flex-wrap gap-3">
              <div>
                <label className="mb-1 block text-xs text-zinc-500">Vendor name</label>
                <Input value={subVendor} onChange={setSubVendor} placeholder="Cloudy SaaS Inc" />
              </div>
              <div>
                <label className="mb-1 block text-xs text-zinc-500">Doc type</label>
                <Select
                  value={subDocType}
                  onChange={setSubDocType}
                  options={DOC_TYPES.map((t) => ({ value: t, label: t }))}
                />
              </div>
            </div>
            <div>
              <label className="mb-1 block text-xs text-zinc-500">Raw text</label>
              <Textarea
                value={subText}
                onChange={setSubText}
                placeholder="We enforce multi-factor authentication for all employee access..."
              />
            </div>
            <Button
              variant="primary"
              disabled={!subVendor || !subText || submitMutation.isPending}
              onClick={() => submitMutation.mutate()}
            >
              {submitMutation.isPending ? "Submitting…" : "Submit"}
            </Button>
            {submitMutation.isError && <ErrorBlock message={(submitMutation.error as ApiError).message} />}
            {submitMutation.isSuccess && (
              <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-3 text-xs">
                <div>
                  armor_verdict:{" "}
                  <Badge tone={submitMutation.data.armor_verdict === "clean" ? "green" : "red"}>
                    {submitMutation.data.armor_verdict}
                  </Badge>
                </div>
                <div className="mt-1 text-zinc-500">status: {submitMutation.data.status}</div>
                <div className="mt-1 text-zinc-500">trace_id: {submitMutation.data.trace_id}</div>
              </div>
            )}
          </div>
        </Card>
      )}

      <Card>
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <Input value={search} onChange={setSearch} placeholder="Search vendors…" className="w-64" />
          <Select
            value={tierFilter}
            onChange={setTierFilter}
            options={[{ value: "", label: "All tiers" }, ...TIERS.map((t) => ({ value: t, label: t }))]}
          />
          {(search || tierFilter) && (
            <span className="text-xs text-zinc-500">
              {filtered.length} of {vendors.data!.length}
            </span>
          )}
        </div>
        {filtered.length === 0 ? (
          <EmptyBlock label="No vendors match." />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th onClick={() => sort.toggle("name")} sortDirection={sort.directionFor("name")}>
                  Name
                </Th>
                <Th onClick={() => sort.toggle("tier")} sortDirection={sort.directionFor("tier")}>
                  Tier
                </Th>
                <Th onClick={() => sort.toggle("status")} sortDirection={sort.directionFor("status")}>
                  Status
                </Th>
                <Th
                  onClick={() => sort.toggle("blind_window_days")}
                  sortDirection={sort.directionFor("blind_window_days")}
                >
                  Blind window
                </Th>
                <Th
                  onClick={() => sort.toggle("last_assessed_at")}
                  sortDirection={sort.directionFor("last_assessed_at")}
                >
                  Last assessed
                </Th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((v) => (
                <Tr key={v.vendor_id} onClick={() => navigate(`/vendors/${v.vendor_id}`)}>
                  <Td className="font-medium text-zinc-100">{v.name}</Td>
                  <Td>
                    <Badge tone={toneForTier(v.tier)}>{v.tier}</Badge>
                  </Td>
                  <Td>
                    <Badge>{v.status}</Badge>
                  </Td>
                  <Td>
                    {v.blind_window_days === null ? (
                      "—"
                    ) : (
                      <span className={v.blind_window_days > 30 ? "text-amber-400" : ""}>
                        {v.blind_window_days}d
                      </span>
                    )}
                  </Td>
                  <Td className="text-zinc-500">{v.last_assessed_at ?? "never"}</Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </div>
  );
}
