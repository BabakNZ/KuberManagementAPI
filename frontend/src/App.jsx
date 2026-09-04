import { useEffect, useState } from "react";
import {
  Activity,
  Box,
  ChevronRight,
  Cloud,
  Database,
  LoaderCircle,
  Plus,
  RefreshCw,
  Server,
  Settings2,
  Trash2,
  X,
} from "lucide-react";
import "./App.css";
import { api, listData } from "./lib/api";
import StatusBadge from "./components/StatusBadge";
import AlertBanner from "./components/AlertBanner";
import ConfirmDialog from "./components/ConfirmDialog";
import Toast from "./components/Toast";

function Metric({ label, value, icon: Icon }) {
  return (
    <div className="metric">
      <Icon size={15} />
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function FormField({
  label,
  name,
  value,
  onChange,
  type = "text",
  placeholder,
  required = true,
  min,
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <input
        name={name}
        value={value ?? ""}
        onChange={onChange}
        type={type}
        placeholder={placeholder}
        required={required}
        min={min}
      />
    </label>
  );
}

function App() {
  const [clusters, setClusters] = useState([]);
  const [namespaces, setNamespaces] = useState([]);
  const [apps, setApps] = useState([]);
  const [selectedCluster, setSelectedCluster] = useState(null);
  const [selectedNamespace, setSelectedNamespace] = useState(null);
  const [selectedApp, setSelectedApp] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [modal, setModal] = useState(null);
  const [confirmation, setConfirmation] = useState(null);
  const [formValues, setFormValues] = useState({});

  const openModal = (kind) => {
    if (kind === "edit" && selectedApp) {
      setFormValues({
        name: selectedApp.name || "",
        image: selectedApp.image || "",
        replicas: selectedApp.replicas ?? 1,
        cpu_request: selectedApp.cpu_request || "",
        cpu_limit: selectedApp.cpu_limit || "",
        memory_request: selectedApp.memory_request || "",
        memory_limit: selectedApp.memory_limit || "",
      });
    } else if (kind === "cluster") {
      setFormValues({ name: "", address: "", token: "" });
    } else if (kind === "namespace") {
      setFormValues({ name: "" });
    } else {
      setFormValues({
        name: "",
        image: "",
        replicas: 1,
        cpu_request: "100m",
        cpu_limit: "500m",
        memory_request: "128Mi",
        memory_limit: "512Mi",
      });
    }
    setModal(kind);
  };

  const updateField = (event) => {
    const { name, value } = event.target;
    setFormValues((current) => ({ ...current, [name]: value }));
  };

  const loadClusters = async () => {
    const data = listData(await api("/api/clusters/"));
    setClusters(data);
    setSelectedCluster(
      (current) =>
        data.find((item) => item.id === current?.id) || data[0] || null,
    );
    return data;
  };
  const loadNamespaces = async (clusterId) => {
    if (!clusterId) {
      setNamespaces([]);
      setSelectedNamespace(null);
      return [];
    }
    const data = listData(
      await api(`/api/namespaces/?cluster_id=${clusterId}`),
    );
    setNamespaces(data);
    setSelectedNamespace(
      (current) =>
        data.find((item) => item.id === current?.id) || data[0] || null,
    );
    return data;
  };
  const loadApps = async (namespaceId) => {
    if (!namespaceId) {
      setApps([]);
      setSelectedApp(null);
      return [];
    }
    const data = listData(await api(`/api/apps/?namespace_id=${namespaceId}`));
    setApps(data);
    setSelectedApp(
      (current) => data.find((item) => item.id === current?.id) || null,
    );
    return data;
  };
  const refresh = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await loadClusters();
      const cluster =
        data.find((item) => item.id === selectedCluster?.id) || data[0];
      const namespaceData = await loadNamespaces(cluster?.id);
      const namespace =
        namespaceData.find((item) => item.id === selectedNamespace?.id) ||
        namespaceData[0];
      await loadApps(namespace?.id);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    refresh();
  }, []);
  useEffect(() => {
    if (selectedCluster)
      loadNamespaces(selectedCluster.id).catch((e) => setError(e.message));
  }, [selectedCluster?.id]);
  useEffect(() => {
    if (selectedNamespace)
      loadApps(selectedNamespace.id).catch((e) => setError(e.message));
  }, [selectedNamespace?.id]);
  const submit = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError("");
    const form = formValues;
    try {
      if (modal === "cluster")
        await api("/api/clusters/", {
          method: "POST",
          body: JSON.stringify(form),
        });
      if (modal === "namespace")
        await api("/api/namespaces/", {
          method: "POST",
          body: JSON.stringify({
            ...form,
            cluster_id: Number(selectedCluster.id),
          }),
        });
      if (modal === "app")
        await api("/api/apps/", {
          method: "POST",
          body: JSON.stringify({
            ...form,
            namespace_id: Number(selectedNamespace.id),
            replicas: Number(form.replicas),
          }),
        });
      if (modal === "edit") {
        const { name: _name, ...changes } = form;
        await api(`/api/apps/${selectedApp.id}/`, {
          method: "PATCH",
          body: JSON.stringify({ ...changes, replicas: Number(form.replicas) }),
        });
      }
      setModal(null);
      setNotice("Changes saved");
      await refresh();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  };
  const remove = async (kind, item) => {
    setSaving(true);
    setError("");
    try {
      await api(`/api/${kind}/${item.id}/`, { method: "DELETE" });
      setSelectedApp(null);
      setNotice(`${kind === "apps" ? "App" : "Namespace"} deleted`);
      setConfirmation(null);
      await refresh();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  };
  const requestRemoval = (kind, item) => {
    setConfirmation({ kind, item });
  };
  const livePods = selectedApp?.live?.pods || [];

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">
            <Cloud size={19} />
          </div>
          <div>
            <strong>Control plane</strong>
            <span>Infrastructure workspace</span>
          </div>
        </div>
        <div className="topbar-actions">
          <span className="connection">
            <span /> API connected
          </span>
          <button
            className="icon-button"
            title="Refresh data"
            aria-label="Refresh data"
            onClick={refresh}
          >
            <RefreshCw size={17} />
          </button>
          <button className="primary" onClick={() => openModal("cluster")}>
            <Plus size={16} /> Register cluster
          </button>
        </div>
      </header>
      <Toast message={notice} onDismiss={() => setNotice("")} />
      <main className="workspace">
        <aside className="sidebar">
          <div className="eyebrow">Your infrastructure</div>
          <div className="side-title">
            <h1>Clusters</h1>
            <span>{clusters.length}</span>
          </div>
          <div className="cluster-list">
            {loading && !clusters.length ? (
              <div className="loading-line">
                <LoaderCircle className="spin" size={16} /> Loading clusters
              </div>
            ) : clusters.length ? (
              clusters.map((cluster) => (
                <button
                  className={`cluster-item ${selectedCluster?.id === cluster.id ? "active" : ""}`}
                  key={cluster.id}
                  onClick={() => {
                    setSelectedCluster(cluster);
                    setSelectedNamespace(null);
                    setSelectedApp(null);
                  }}
                >
                  <span className="cluster-icon">
                    <Server size={17} />
                  </span>
                  <span className="cluster-copy">
                    <strong>{cluster.name}</strong>
                    <small>{cluster.address}</small>
                  </span>
                  <ChevronRight size={15} />
                </button>
              ))
            ) : (
              <div className="empty-side">
                <Server size={20} />
                <p>No clusters registered</p>
                <button onClick={() => openModal("cluster")}>
                  Register one
                </button>
              </div>
            )}
          </div>
          <div className="sidebar-foot">
            <Activity size={15} />
            <span>Live operations</span>
            <span className="pulse" />
          </div>
        </aside>
        <section className="content">
          <div className="page-heading">
            <div>
              <div className="breadcrumb">
                <span>Clusters</span>
                <ChevronRight size={13} />
                <strong>{selectedCluster?.name || "Select a cluster"}</strong>
              </div>
              <h2>
                {selectedCluster
                  ? selectedCluster.name
                  : "Welcome to your control plane"}
              </h2>
              <p>
                {selectedCluster
                  ? selectedCluster.address
                  : "Register a cluster to begin managing namespaces and applications."}
              </p>
            </div>
            {selectedCluster && (
              <button
                className="secondary"
                onClick={() => openModal("namespace")}
              >
                <Plus size={16} /> New namespace
              </button>
            )}
          </div>
          <AlertBanner message={error} onDismiss={() => setError("")} />
          {selectedCluster && (
            <>
              <div className="section-label">
                Namespaces <span>{namespaces.length}</span>
              </div>
              <div className="namespace-strip">
                {namespaces.length ? (
                  namespaces.map((namespace) => (
                    <button
                      key={namespace.id}
                      className={`namespace-card ${selectedNamespace?.id === namespace.id ? "selected" : ""}`}
                      onClick={() => {
                        setSelectedNamespace(namespace);
                        setSelectedApp(null);
                      }}
                    >
                      <div className="namespace-top">
                        <Box size={16} />
                        <StatusBadge status={namespace.status} />
                      </div>
                      <strong>{namespace.name}</strong>
                      <small>
                        Namespace <ChevronRight size={12} />
                      </small>
                    </button>
                  ))
                ) : (
                  <div className="empty-panel">
                    <Database size={22} />
                    <div>
                      <strong>No namespaces yet</strong>
                      <p>
                        Create a namespace in this cluster to deploy an app.
                      </p>
                    </div>
                  </div>
                )}
              </div>
            </>
          )}
          <div className="section-label app-label">
            Applications {selectedNamespace && <span>{apps.length}</span>}
            {selectedNamespace && (
              <button className="text-button" onClick={() => openModal("app")}>
                <Plus size={15} /> Create app
              </button>
            )}
          </div>
          <div className="table-wrap">
            {!selectedNamespace ? (
              <div className="empty-state">
                <Box size={32} />
                <strong>Select a namespace</strong>
                <p>Choose a namespace above to view its applications.</p>
              </div>
            ) : apps.length ? (
              <table>
                <thead>
                  <tr>
                    <th>Application</th>
                    <th>State</th>
                    <th>Image</th>
                    <th>Replicas</th>
                    <th>Resources</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {apps.map((app) => (
                    <tr
                      key={app.id}
                      className={
                        selectedApp?.id === app.id ? "row-selected" : ""
                      }
                      onClick={() => setSelectedApp(app)}
                    >
                      <td>
                        <div className="app-name">
                          <span className="app-avatar">
                            <Box size={15} />
                          </span>
                          <strong>{app.name}</strong>
                        </div>
                      </td>
                      <td>
                        <StatusBadge status={app.status} />
                      </td>
                      <td>
                        <code>{app.image}</code>
                      </td>
                      <td>
                        <strong>
                          {app.live?.ready_replicas ?? app.replicas}
                        </strong>
                        <span className="muted"> / {app.replicas}</span>
                      </td>
                      <td>
                        <span className="resource-copy">
                          {app.cpu_request || "—"} CPU
                          <br />
                          {app.memory_request || "—"} RAM
                        </span>
                      </td>
                      <td>
                        <ChevronRight size={16} className="row-arrow" />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="empty-state">
                <Box size={32} />
                <strong>No applications in {selectedNamespace.name}</strong>
                <p>Deploy your first application to this namespace.</p>
                <button className="primary" onClick={() => openModal("app")}>
                  <Plus size={15} /> Create application
                </button>
              </div>
            )}
          </div>
        </section>
        {selectedApp && (
          <aside className="detail-panel">
            <div className="detail-head">
              <div>
                <div className="eyebrow">Application detail</div>
                <h3>{selectedApp.name}</h3>
              </div>
              <button
                className="icon-button"
                aria-label="Close application details"
                onClick={() => setSelectedApp(null)}
              >
                <X size={17} />
              </button>
            </div>
            <div className="detail-status">
              <StatusBadge status={selectedApp.status} />
              <span>
                {selectedApp.updated_at
                  ? `Updated ${new Date(selectedApp.updated_at).toLocaleDateString()}`
                  : "Live status"}
              </span>
            </div>
            <div className="detail-block">
              <span className="detail-label">Deployment</span>
              <div className="detail-line">
                <span>Image</span>
                <code>{selectedApp.image}</code>
              </div>
              <div className="detail-line">
                <span>Namespace</span>
                <strong>{selectedNamespace?.name}</strong>
              </div>
              <div className="detail-line">
                <span>Replicas</span>
                <strong>{selectedApp.replicas}</strong>
              </div>
            </div>
            <div className="detail-block">
              <span className="detail-label">Live pods</span>
              {livePods.length ? (
                livePods.map((pod) => (
                  <div className="pod-row" key={pod.name || pod.id}>
                    <span className="pod-dot" />
                    <span>{pod.name || "Pod"}</span>
                    <StatusBadge status={pod.status || "Ready"} />
                  </div>
                ))
              ) : (
                <div className="live-empty">
                  {selectedApp.live?.error || "No live pod data available"}
                </div>
              )}
            </div>
            <div className="detail-block">
              <span className="detail-label">Resources</span>
              <Metric
                label="CPU request"
                value={selectedApp.cpu_request || "—"}
                icon={Activity}
              />
              <Metric
                label="CPU limit"
                value={selectedApp.cpu_limit || "—"}
                icon={Activity}
              />
              <Metric
                label="Memory request"
                value={selectedApp.memory_request || "—"}
                icon={Database}
              />
              <Metric
                label="Memory limit"
                value={selectedApp.memory_limit || "—"}
                icon={Database}
              />
            </div>
            <div className="detail-actions">
              <button className="secondary" onClick={() => openModal("edit")}>
                <Settings2 size={15} /> Edit app
              </button>
              <button
                className="danger-button"
                onClick={() => requestRemoval("apps", selectedApp)}
              >
                <Trash2 size={15} /> Delete
              </button>
            </div>
          </aside>
        )}
      </main>
      {selectedNamespace && (
        <button
          className="floating-delete"
          title="Delete namespace"
          onClick={() => requestRemoval("namespaces", selectedNamespace)}
        >
          <Trash2 size={15} /> Delete namespace
        </button>
      )}
      {modal && (
        <div
          className="modal-backdrop"
          onMouseDown={(event) =>
            event.target === event.currentTarget && setModal(null)
          }
        >
          <div className="modal">
            <div className="modal-head">
              <div>
                <div className="eyebrow">Configuration</div>
                <h3>
                  {modal === "cluster"
                    ? "Register cluster"
                    : modal === "namespace"
                      ? "Create namespace"
                      : modal === "edit"
                        ? `Edit ${selectedApp.name}`
                        : "Create application"}
                </h3>
              </div>
              <button
                className="icon-button"
                aria-label="Close dialog"
                onClick={() => setModal(null)}
              >
                <X size={17} />
              </button>
            </div>
            <form onSubmit={submit}>
              {modal === "cluster" && (
                <>
                  <FormField
                    label="Cluster name"
                    name="name"
                    value={formValues.name}
                    onChange={updateField}
                    placeholder="production"
                  />
                  <FormField
                    label="API address"
                    name="address"
                    value={formValues.address}
                    onChange={updateField}
                    placeholder="https://api.example.com:6443"
                  />
                  <label className="field">
                    <span>Bearer token</span>
                    <textarea
                      name="token"
                      rows="3"
                      value={formValues.token || ""}
                      onChange={updateField}
                      required
                      placeholder="Paste the cluster token"
                    />
                  </label>
                </>
              )}
              {modal === "namespace" && (
                <FormField
                  label="Namespace name"
                  name="name"
                  value={formValues.name}
                  onChange={updateField}
                  placeholder="staging"
                />
              )}
              {(modal === "app" || modal === "edit") && (
                <>
                  <div className="form-grid">
                    <FormField
                      label="App name"
                      name="name"
                      value={formValues.name}
                      onChange={updateField}
                      placeholder="web"
                      required={modal === "app"}
                    />
                    <FormField
                      label="Container image"
                      name="image"
                      value={formValues.image}
                      onChange={updateField}
                      placeholder="nginx:1.27"
                    />
                  </div>
                  <div className="form-grid">
                    <FormField
                      label="Replicas"
                      name="replicas"
                      type="number"
                      min="0"
                      value={formValues.replicas}
                      onChange={updateField}
                    />
                    <FormField
                      label="CPU request"
                      name="cpu_request"
                      value={formValues.cpu_request}
                      onChange={updateField}
                      placeholder="100m"
                    />
                  </div>
                  <div className="form-grid">
                    <FormField
                      label="CPU limit"
                      name="cpu_limit"
                      value={formValues.cpu_limit}
                      onChange={updateField}
                      placeholder="500m"
                    />
                    <FormField
                      label="Memory request"
                      name="memory_request"
                      value={formValues.memory_request}
                      onChange={updateField}
                      placeholder="128Mi"
                    />
                  </div>
                  <FormField
                    label="Memory limit"
                    name="memory_limit"
                    value={formValues.memory_limit}
                    onChange={updateField}
                    placeholder="512Mi"
                  />
                </>
              )}
              {
                <div className="modal-actions">
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => setModal(null)}
                  >
                    Cancel
                  </button>
                  <button className="primary" disabled={saving}>
                    {saving && <LoaderCircle className="spin" size={15} />}
                    {modal === "edit" ? "Save changes" : "Create"}
                  </button>
                </div>
              }
            </form>
          </div>
        </div>
      )}
      {confirmation && (
        <ConfirmDialog
          title={`Delete ${confirmation.item.name}?`}
          description="This removes the resource from Kubernetes and cannot be undone."
          busy={saving}
          onCancel={() => setConfirmation(null)}
          onConfirm={() => remove(confirmation.kind, confirmation.item)}
        />
      )}
    </div>
  );
}

export default App;
