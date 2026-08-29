import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApi, ApiError } from "../lib/api";
import { useSort } from "../lib/sort";
import { formatDate } from "../lib/format";
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
import { FileText, Plus, Upload } from "lucide-react";

const DOC_TYPES = ["SOC2", "ISO", "pen-test", "DPA", "MSA", "contract", "SLA", "order form"];
const TIERS = ["critical", "high", "moderate", "low"];
const NEW_VENDOR = "__new__";
const ACCEPTED_EXTENSIONS = [".pdf", ".docx", ".txt"];
const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

export default function Vendors() {
  const api = useApi();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const [tierFilter, setTierFilter] = useState("");
  const [showRegister, setShowRegister] = useState(false);
  const [showSubmit, setShowSubmit] = useState(searchParams.get("submit") === "1");
  const sort = useSort<Vendor>();

  const vendors = useQuery({ queryKey: ["vendors"], queryFn: () => api.listVendors() });

  // Deep-link from a vendor's empty Contract terms/Subprocessors tab
  // ("Upload a contract for X") -- pre-fills and opens the form, then
  // clears the query string so a refresh doesn't re-trigger it.
  useEffect(() => {
    const wantsSubmit = searchParams.get("submit") === "1";
    if (!wantsSubmit) return;
    setShowSubmit(true);
    const deepLinkVendor = searchParams.get("vendor");
    if (deepLinkVendor) setSubVendorChoice(deepLinkVendor);
    const deepLinkDocType = searchParams.get("docType");
    if (deepLinkDocType && DOC_TYPES.includes(deepLinkDocType)) setSubDocType(deepLinkDocType);
    setSearchParams({}, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  const [subVendorChoice, setSubVendorChoice] = useState(NEW_VENDOR);
  const [subNewVendorName, setSubNewVendorName] = useState("");
  const [subDocType, setSubDocType] = useState(DOC_TYPES[0]);
  const [subMode, setSubMode] = useState<"upload" | "paste">("upload");
  const [subFile, setSubFile] = useState<File | null>(null);
  const [subFileError, setSubFileError] = useState<string | null>(null);
  const [subText, setSubText] = useState("");

  const subVendorName = subVendorChoice === NEW_VENDOR ? subNewVendorName : subVendorChoice;

  const submitMutation = useMutation({
    mutationFn: () =>
      subMode === "upload" && subFile
        ? api.uploadArtifact({ vendor_name: subVendorName, doc_type: subDocType, file: subFile })
        : api.submitArtifact({ vendor_name: subVendorName, doc_type: subDocType, raw_text: subText }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["vendors"] });
      qc.invalidateQueries({ queryKey: ["vendor-contract-terms"] });
      qc.invalidateQueries({ queryKey: ["vendor-subprocessors"] });
      setSubVendorChoice(NEW_VENDOR);
      setSubNewVendorName("");
      setSubFile(null);
      setSubText("");
    },
  });

  function pickFile(file: File | null) {
    setSubFileError(null);
    if (!file) {
      setSubFile(null);
      return;
    }
    const ext = "." + (file.name.split(".").pop() ?? "").toLowerCase();
    if (!ACCEPTED_EXTENSIONS.includes(ext)) {
      setSubFileError(`Unsupported file type "${ext}" — only ${ACCEPTED_EXTENSIONS.join(", ")} are accepted.`);
      setSubFile(null);
      return;
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      setSubFileError(`File too large (${(file.size / 1024 / 1024).toFixed(1)} MB, max 10 MB).`);
      setSubFile(null);
      return;
    }
    setSubFile(file);
  }

  const canSubmit =
    !!subVendorName &&
    (subMode === "upload" ? !!subFile && !subFileError : !!subText.trim()) &&
    !submitMutation.isPending;

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
          subtitle={
            subMode === "upload"
              ? "POST /vendors/artifacts/upload — extracted server-side, then screened by Model Armor before any LLM call; requires Gemini credentials to run the full Onboard/Assure loop"
              : "POST /vendors/artifacts — screened by Model Armor before any LLM call; requires Gemini credentials to run the full Onboard/Assure loop"
          }
        >
          <div className="space-y-3">
            <div className="flex flex-wrap gap-3">
              <div>
                <label className="mb-1 block text-xs text-zinc-500">Vendor</label>
                <Select
                  value={subVendorChoice}
                  onChange={setSubVendorChoice}
                  options={[
                    { value: NEW_VENDOR, label: "+ New vendor…" },
                    ...(vendors.data ?? []).map((v) => ({ value: v.name, label: v.name })),
                  ]}
                  className="w-56"
                />
              </div>
              {subVendorChoice === NEW_VENDOR && (
                <div>
                  <label className="mb-1 block text-xs text-zinc-500">New vendor name</label>
                  <Input value={subNewVendorName} onChange={setSubNewVendorName} placeholder="Cloudy SaaS Inc" />
                </div>
              )}
              <div>
                <label className="mb-1 block text-xs text-zinc-500">Doc type</label>
                <Select
                  value={subDocType}
                  onChange={setSubDocType}
                  options={DOC_TYPES.map((t) => ({ value: t, label: t }))}
                />
              </div>
            </div>

            <div className="flex gap-1 border-b border-zinc-800">
              <button
                type="button"
                onClick={() => setSubMode("upload")}
                className={`flex items-center gap-1.5 border-b-2 px-3 py-1.5 text-xs font-medium transition-colors ${
                  subMode === "upload"
                    ? "border-indigo-500 text-zinc-100"
                    : "border-transparent text-zinc-500 hover:text-zinc-300"
                }`}
              >
                <Upload className="h-3.5 w-3.5" /> Upload document
              </button>
              <button
                type="button"
                onClick={() => setSubMode("paste")}
                className={`flex items-center gap-1.5 border-b-2 px-3 py-1.5 text-xs font-medium transition-colors ${
                  subMode === "paste"
                    ? "border-indigo-500 text-zinc-100"
                    : "border-transparent text-zinc-500 hover:text-zinc-300"
                }`}
              >
                <FileText className="h-3.5 w-3.5" /> Paste text
              </button>
            </div>

            {subMode === "upload" ? (
              <div>
                <label
                  htmlFor="artifact-file"
                  className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-zinc-700 bg-zinc-900/50 px-4 py-8 text-center hover:border-indigo-500"
                >
                  <Upload className="h-5 w-5 text-zinc-500" />
                  {subFile ? (
                    <div className="text-sm text-zinc-200">
                      {subFile.name} <span className="text-zinc-500">({(subFile.size / 1024).toFixed(0)} KB)</span>
                    </div>
                  ) : (
                    <div className="text-sm text-zinc-500">
                      Click to choose a file, or drag one here — PDF, DOCX, or TXT (max 10 MB)
                    </div>
                  )}
                </label>
                <input
                  id="artifact-file"
                  type="file"
                  accept={ACCEPTED_EXTENSIONS.join(",")}
                  className="hidden"
                  onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
                />
                {subFileError && <div className="mt-2 text-xs text-rose-400">{subFileError}</div>}
              </div>
            ) : (
              <div>
                <label className="mb-1 block text-xs text-zinc-500">Raw text</label>
                <Textarea
                  value={subText}
                  onChange={setSubText}
                  placeholder="We enforce multi-factor authentication for all employee access..."
                />
              </div>
            )}

            <Button variant="primary" disabled={!canSubmit} onClick={() => submitMutation.mutate()}>
              {submitMutation.isPending ? "Submitting…" : "Submit"}
            </Button>
            {submitMutation.isError && <ErrorBlock message={(submitMutation.error as ApiError).message} />}
            {submitMutation.isSuccess && (
              <div
                className={`rounded-lg border p-3 text-xs ${
                  submitMutation.data.armor_verdict === "clean"
                    ? "border-emerald-900/60 bg-emerald-950/30"
                    : "border-rose-900/60 bg-rose-950/40"
                }`}
              >
                <div className="flex items-center gap-2">
                  <span className="font-medium text-zinc-200">
                    {submitMutation.data.armor_verdict === "clean"
                      ? "Screened clean by Model Armor"
                      : "Blocked by Model Armor"}
                  </span>
                  <Badge tone={submitMutation.data.armor_verdict === "clean" ? "green" : "red"}>
                    {submitMutation.data.armor_verdict}
                  </Badge>
                </div>
                <div className="mt-1 text-zinc-500">status: {submitMutation.data.status}</div>
                <div className="mt-1 text-zinc-500">
                  trace_id:{" "}
                  <Link
                    to={`/traces?trace=${encodeURIComponent(submitMutation.data.trace_id)}`}
                    className="text-indigo-400 hover:underline"
                  >
                    {submitMutation.data.trace_id}
                  </Link>
                </div>
                {submitMutation.data.summary && (
                  <div className="mt-1 text-zinc-500">{submitMutation.data.summary}</div>
                )}
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
                  <Td className="text-zinc-500">{v.last_assessed_at ? formatDate(v.last_assessed_at) : "never"}</Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </div>
  );
}
