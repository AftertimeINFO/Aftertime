import { useCallback, useEffect, useRef, useState } from "react";
import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type Node,
  type ReactFlowInstance,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { api, type PortContract, type Row, type Workspace } from "./api";
import {
  diagnosticSeriesDash,
  diagnosticSeriesStats,
  diagnosticSeriesValue,
  formatDiagnosticValue,
  preferredDiagnosticPoint,
  resolveSeriesNodeId,
} from "./chartNavigation";
import { DEFAULT_SCENARIO_ID, shouldAutoStartDefaultScenario } from "./startup";

const palette: Record<string, string> = {
  resource: "#64d8cb",
  gas: "#77bdfb",
  generation: "#f0bd63",
  substation: "#d899ff",
  line: "#ff8f72",
  grid: "#b7f34a",
  end_product: "#f3f3f0",
  start: "#64d8cb",
  event_trigger: "#ff8f72",
  python_action: "#d899ff",
  resource_operation: "#f0bd63",
  wait: "#77bdfb",
  component_command: "#b7f34a",
  metric_check: "#70d6ff",
  success: "#82e072",
  failure: "#ff786d",
};
const clock = (value?: string) =>
  value
    ? new Intl.DateTimeFormat("uk-UA", {
        timeZone: "Europe/Kyiv",
        dateStyle: "medium",
        timeStyle: "short",
      }).format(new Date(value))
    : "—";
const pct = (value: number, min: number, max: number) =>
  Math.max(0, Math.min(100, ((value - min) / Math.max(1, max - min)) * 100));
function GraphNode({ data, selected }: any) {
  const inputs = (data.ports || []).filter((port: PortContract) => port.direction !== "output"),
    outputs = (data.ports || []).filter((port: PortContract) => port.direction !== "input");
  return (
    <div
      className={`model-node ${selected ? "selected" : ""} ${data.online === false ? "offline" : ""}`}
      style={{ "--node": palette[data.category] || "#b7f34a" } as any}
    >
      {inputs.map((port: PortContract, index: number) => <Handle className={`typed-port domain-${port.domain.replaceAll(".", "-")}`} title={`${port.name} · ${port.domain}`} type="target" id={port.key} position={Position.Left} style={{ top: `${((index + 1) * 100) / (inputs.length + 1)}%` }} key={`in-${port.key}`} />)}
      <small>
        {data.level || "FLOW"} · {data.category}
      </small>
      <b>{data.label}</b>
      <span>
        {data.online === false
          ? "ВІДКЛЮЧЕНО"
          : data.output || data.eventType || "готовий"}
      </span>
      <div className="node-port-summary">
        {inputs.map((port: PortContract) => <em title={`${port.domain} · ${port.quantity}`} key={`summary-in-${port.key}`}>→ {port.name}</em>)}
        {outputs.map((port: PortContract) => <em title={`${port.domain} · ${port.quantity}`} key={`summary-out-${port.key}`}>{port.name} →</em>)}
      </div>
      <div className="node-domains">{[...new Set((data.ports || []).map((port: PortContract) => port.domain))].map((domain: any) => <em key={domain}>{domain}</em>)}</div>
      {outputs.map((port: PortContract, index: number) => <Handle className={`typed-port domain-${port.domain.replaceAll(".", "-")}`} title={`${port.name} · ${port.domain}`} type="source" id={port.key} position={Position.Right} style={{ top: `${((index + 1) * 100) / (outputs.length + 1)}%` }} key={`out-${port.key}`} />)}
    </div>
  );
}
const nodeTypes = { lab: GraphNode, workflow: GraphNode };

export default function App() {
  const [w, setW] = useState<Workspace | null>(null),
    [projectId, setProjectId] = useState(""),
    [mode, setMode] = useState<"model" | "process">("model"),
    [viewVersion, setViewVersion] = useState<Row | null>(null),
    [graphRows, setGraphRows] = useState<Row[]>([]),
    [edgeRows, setEdgeRows] = useState<Row[]>([]),
    [observables, setObservables] = useState<any[]>([]),
    [workflow, setWorkflow] = useState<Row | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [selectedId, setSelectedId] = useState<string | null>(null),
    [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null),
    [sideTab, setSideTab] = useState("element"),
    [detailTab, setDetailTab] = useState("parameters"),
    [run, setRun] = useState<Row | null>(null),
    [test, setTest] = useState<Row | null>(null),
    [validation, setValidation] = useState<Row | null>(null),
    [scenario, setScenario] = useState(DEFAULT_SCENARIO_ID),
    [timeline, setTimeline] = useState<Row | null>(null),
    [flow, setFlow] = useState<ReactFlowInstance<Node, Edge> | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]),
    [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const autoStartRequested = useRef(false);
  const modelNodes = useCallback(
    (rows: Row[], components: Row[]) =>
      rows.map((n) => {
        const c = components.find((x) => x.id === n.component_type_id);
        return {
          id: n.id,
          type: "lab",
          position: { x: n.x, y: n.y },
          data: {
            label: n.name,
            category: c?.category,
            level: c?.level,
            online: true,
            ports: c?.ports || [],
          },
        };
      }),
    [],
  );
  const modelEdges = (rows: Row[]) =>
    rows.map((e) => ({
      id: e.id,
      source: e.source_node_id,
      target: e.target_node_id,
      sourceHandle: e.source_port,
      targetHandle: e.target_port,
      label: e.flow_type,
      animated: e.enabled !== false,
      className: `domain-edge domain-${String(e.domain || e.flow_type).replaceAll(".", "-")}`,
      data: e,
    }));
  const workflowNodes = (rows: Row[]) =>
    rows.map((n) => ({
      id: n.id,
      type: "workflow",
      position: { x: n.x, y: n.y },
      data: {
        label: n.name,
        category: n.block_type,
        level: n.block_type,
        eventType: n.config?.event_type,
      },
    }));
  const workflowEdges = (rows: Row[]) =>
    rows.map((e) => ({
      id: e.id,
      source: e.source_node_id,
      target: e.target_node_id,
      label: e.condition_code || "True",
      animated: true,
    }));
  const refresh = useCallback(async () => {
    try {
      const next = await api.workspace(projectId || undefined);
      setW(next);
      setProjectId(next.project.id);
      setViewVersion(next.version);
      setGraphRows(next.nodes);
      setEdgeRows(next.edges);
      setObservables(next.observables || []);
      setNodes(modelNodes(next.nodes, next.components));
      setEdges(modelEdges(next.edges));
    } catch (e) {
      setError(String(e));
    }
  }, [setNodes, setEdges, modelNodes, projectId]);
  useEffect(() => {
    refresh();
  }, [refresh]);
  useEffect(() => {
    if (!w) return;
    const item = w.scenarios.find((x) => x.id === scenario);
    setRun(null);
    setSelectedId(null);
    api
      .scenarioTimeline(scenario)
      .then(setTimeline)
      .catch((e) => setError(String(e)));
    if (!item?.model_version_id) return;
    api
      .graph(scenario === "baseline" ? w.version.id : item.model_version_id)
      .then((graph) => {
        setViewVersion(graph.version);
        setGraphRows(graph.nodes);
        setEdgeRows(graph.edges);
        setObservables(graph.observables || []);
        setNodes(modelNodes(graph.nodes, w.components));
        setEdges(modelEdges(graph.edges));
      })
      .catch((e) => setError(String(e)));
    const workflowId = item.configuration?.workflow_version_id;
    if (workflowId)
      api
        .workflow(workflowId)
        .then(setWorkflow)
        .catch((e) => setError(String(e)));
    else setWorkflow(null);
  }, [scenario, w, setNodes, setEdges, modelNodes]);
  useEffect(() => {
    if (mode === "process") {
      if (workflow) {
        setNodes(workflowNodes(workflow.nodes));
        setEdges(workflowEdges(workflow.transitions));
      } else {
        setNodes([]);
        setEdges([]);
      }
    } else if (w) {
      setNodes(modelNodes(graphRows, w.components));
      api
        .graph(viewVersion?.id || w.version.id)
        .then((g) => setEdges(modelEdges(g.edges)))
        .catch(() => {});
    }
  }, [
    mode,
    workflow,
    w,
    graphRows,
    viewVersion,
    setNodes,
    setEdges,
    modelNodes,
  ]);
  useEffect(() => {
    if (!run?.id || ["completed", "failed", "stopped"].includes(run.status))
      return;
    const id = setInterval(
      () =>
        api
          .getRun(run.id)
          .then(setRun)
          .catch(() => {}),
      650,
    );
    return () => clearInterval(id);
  }, [run?.id, run?.status]);
  useEffect(() => {
    if (mode !== "model" || !run?.state?.nodes || !w) return;
    setNodes((old) =>
      old.map((n) => {
        const type = graphRows.find(
          (item) => item.id === n.id,
        )?.component_type_id;
        const current =
          run.state.nodes[n.id] ||
          Object.entries(run.state.nodes).find(([id]) =>
            id.endsWith(`-${type}`),
          )?.[1] ||
          {};
        return {
          ...n,
          data: {
            ...n.data,
            online: (current as any).state?.online,
            output: Object.entries((current as any).outputs || {})
              .slice(0, 2)
              .map(([k, v]) => `${k} ${Number(v).toFixed(1)}`)
              .join(" · "),
          },
        };
      }),
    );
  }, [run?.state, w, graphRows, mode, setNodes]);
  const selected =
      mode === "model"
        ? graphRows.find((n) => n.id === selectedId)
        : workflow?.nodes?.find((n: Row) => n.id === selectedId),
    component = w?.components.find((c) => c.id === selected?.component_type_id),
    selectedEdge = edgeRows.find((edge) => edge.id === selectedEdgeId),
    immutable =
      mode === "model"
        ? viewVersion?.status !== "draft"
        : workflow?.version?.status !== "draft";
  const mutate = async (task: () => Promise<any>) => {
    setBusy(true);
    setError("");
    try {
      await task();
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };
  const connect = (c: Connection) => {
    if (!c.source || !c.target || !w || !viewVersion) return;
    if (mode === "model")
      mutate(() =>
        api.addEdge(viewVersion.id, {
          source_node_id: c.source,
          source_port: c.sourceHandle || "out",
          target_node_id: c.target,
          target_port: c.targetHandle || "in",
        }),
      );
    else if (workflow)
      mutate(() =>
        api.addWorkflowTransition(workflow.version.id, {
          source_node_id: c.source,
          target_node_id: c.target,
          condition_code: "True",
        }),
      );
  };
  const validConnection = useCallback((connection: Connection | Edge) => {
    const sourceNode = nodes.find((node) => node.id === connection.source), targetNode = nodes.find((node) => node.id === connection.target);
    const source = ((sourceNode?.data as any)?.ports || []).find((port: PortContract) => port.key === connection.sourceHandle),
      target = ((targetNode?.data as any)?.ports || []).find((port: PortContract) => port.key === connection.targetHandle);
    return Boolean(source && target && source.direction !== "input" && target.direction !== "output" && source.domain === target.domain && source.quantity === target.quantity);
  }, [nodes]);
  const drop = async (e: React.DragEvent) => {
    e.preventDefault();
    if (immutable || !w) return;
    const bounds = (e.currentTarget as HTMLElement).getBoundingClientRect(),
      position = {
        x: e.clientX - bounds.left - 90,
        y: e.clientY - bounds.top - 35,
      };
    try {
      if (mode === "model") {
        const componentId = e.dataTransfer.getData("model");
        if (!componentId) return;
        await api.addNode(viewVersion?.id || w.version.id, {
          component_type_id: componentId,
          name:
            w.components.find((c) => c.id === componentId)?.name ||
            "Новий елемент",
          x: position.x,
          y: position.y,
        });
      } else if (workflow) {
        const blockType = e.dataTransfer.getData("process");
        if (!blockType) return;
        await api.addWorkflowNode(workflow.version.id, {
          name: blockType.replaceAll("_", " "),
          block_type: blockType,
          x: position.x,
          y: position.y,
          config: {},
        });
      }
      await refresh();
      if (mode === "process" && workflow)
        setWorkflow(await api.workflow(workflow.version.id));
    } catch (err) {
      setError(String(err));
    }
  };
  const runModel = async (settings: Row = {}) => {
    if (!w) return;
    try {
      setBusy(true);
      setError("");
      const started = await api.startRun({
        model_version_id: w.project.published_version_id,
        scenario_id: scenario,
        ...settings,
      });
      setRun(await api.getRun(started.id));
      setSideTab("events");
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    const selectedScenario = w?.scenarios.find((item) => item.id === scenario);
    if (!shouldAutoStartDefaultScenario({
      scenarioId: scenario,
      scenarioModelVersionId: selectedScenario?.model_version_id,
      loadedModelVersionId: viewVersion?.id,
      timelineReady: Boolean(timeline),
      runExists: Boolean(run),
      alreadyRequested: autoStartRequested.current,
    })) return;
    autoStartRequested.current = true;
    void runModel();
  }, [scenario, timeline, viewVersion?.id, w, run]);
  const focusGraphNode = useCallback((nodeId: string) => {
    if (!graphRows.some((node) => node.id === nodeId)) return;
    setMode("model");
    setSelectedId(nodeId);
    setSelectedEdgeId(null);
    setSideTab("element");
    setDetailTab("monitoring");
    window.setTimeout(() => {
      flow?.fitView({ nodes: [{ id: nodeId }], padding: 1.5, duration: 550 });
      document.querySelector(".canvas")?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 0);
  }, [flow, graphRows]);
  if (!w)
    return <div className="loading">MODEL LAB · завантаження… {error}</div>;
  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand">
          <i />
          <span>
            <b>AFTERTIME</b>
            <small>MODEL LAB · SCRIPTED RUNTIME</small>
          </span>
        </div>
        <div className="title">
          <small>ВИКОНУВАНА МОДЕЛЬ · БЕЗ ТЕРИТОРІЙ</small>
          <b>
            {mode === "process"
              ? workflow?.version?.name || "Process Designer"
              : viewVersion?.name || w.project.name}
          </b>
        </div>
        <div className="model-tools">
          <select aria-label="Модель" value={w.project.id} onChange={(event) => { setProjectId(event.target.value); setSelectedId(null); setSelectedEdgeId(null); }}>
            {(w.projects || [w.project]).map((project: Row) => <option value={project.id} key={project.id}>{project.name}</option>)}
          </select>
          <button onClick={async () => {
            const name = window.prompt("Назва нової моделі");
            if (!name) return;
            const created = await api.createProject({ name, version_name: name });
            setProjectId(created.project.id);
          }}>＋ Нова модель</button>
        </div>
        <div className="mode-switch">
          <button
            className={mode === "model" ? "active" : ""}
            onClick={() => {
              setMode("model");
              setSelectedId(null);
            }}
          >
            Модель
          </button>
          <button
            className={mode === "process" ? "active" : ""}
            onClick={() => {
              setMode("process");
              setSelectedId(null);
            }}
          >
            Process Designer
          </button>
        </div>
        <div className="version">
          <span
            className={
              mode === "process"
                ? workflow?.version?.status
                : viewVersion?.status
            }
          >
            {mode === "process"
              ? workflow?.version?.status || "—"
              : viewVersion?.status}
          </span>
          <b>
            v
            {mode === "process"
              ? workflow?.version?.version || "—"
              : viewVersion?.version}
          </b>
        </div>
      </header>
      {error && (
        <div className="error">
          {error}
          <button onClick={() => setError("")}>×</button>
        </div>
      )}
      <section className="workbench">
        <Palette mode={mode} w={w} disabled={immutable} />
        <section
          className="canvas"
          onDragOver={(e) => e.preventDefault()}
          onDrop={drop}
        >
          <div className="toolbar">
            {mode === "model" ? (
              <>
                {immutable && viewVersion && <button onClick={() => mutate(() => api.clone(viewVersion.id))}>Створити draft-копію</button>}
                <button
                  disabled={immutable}
                  onClick={() =>
                    mutate(async () =>
                      setValidation(await api.validate(viewVersion?.id || w.version.id)),
                    )
                  }
                >
                  ✓ Перевірити
                </button>
                <button
                  disabled={immutable || !validation?.valid}
                  onClick={() => mutate(() => api.publish(viewVersion?.id || w.version.id))}
                >
                  Опублікувати
                </button>
              </>
            ) : (
              <>
                {immutable && workflow && (
                  <button
                    onClick={async () => {
                      const draft = await api.cloneWorkflow(
                        workflow.version.id,
                      );
                      setWorkflow(draft);
                      setValidation(null);
                    }}
                  >
                    Створити draft-копію
                  </button>
                )}
                <button
                  disabled={immutable || !workflow}
                  onClick={async () =>
                    workflow &&
                    setValidation(
                      await api.validateWorkflow(workflow.version.id),
                    )
                  }
                >
                  ✓ Перевірити workflow
                </button>
                <button
                  disabled={immutable || !workflow || !validation?.valid}
                  onClick={async () => {
                    if (!workflow) return;
                    await api.publishWorkflow(workflow.version.id);
                    setWorkflow(await api.workflow(workflow.version.id));
                  }}
                >
                  Опублікувати workflow
                </button>
              </>
            )}
            <span>
              {immutable ? "Immutable snapshot · " : "Draft · "}
              {nodes.length} вузлів · {edges.length} зв’язків
            </span>
          </div>
          <ReactFlow
            onInit={setFlow}
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            nodesDraggable={!immutable}
            nodesConnectable={!immutable}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={connect}
            isValidConnection={mode === "model" ? validConnection : undefined}
            onNodeClick={(_, n) => {
              setSelectedId(n.id);
              setSelectedEdgeId(null);
              setSideTab(mode === "process" ? "process" : "element");
            }}
            onEdgeClick={(_, edge) => {
              if (mode !== "model") return;
              setSelectedEdgeId(edge.id);
              setSelectedId(null);
              setSideTab("element");
            }}
            onNodeDragStop={(_, n) => {
              if (immutable) return;
              if (mode === "model")
                api.updateNode(n.id, { x: n.position.x, y: n.position.y });
              else
                api.updateWorkflowNode(n.id, {
                  x: n.position.x,
                  y: n.position.y,
                });
            }}
            fitView
          >
            <Background gap={20} color="#17332b" />
            <MiniMap
              pannable
              zoomable
              nodeColor={(n) => palette[(n.data as any).category]}
            />
            <Controls />
          </ReactFlow>
        </section>
        <RightPanel
          run={run}
          timeline={timeline}
          selected={selected}
          selectedEdge={selectedEdge}
          component={component}
          w={{ ...w, observables }}
          viewVersion={viewVersion}
          scenario={scenario}
          workflow={workflow}
          sideTab={sideTab}
          setSideTab={setSideTab}
          detailTab={detailTab}
          setDetailTab={setDetailTab}
          immutable={immutable}
          test={test}
          setTest={setTest}
          mutate={mutate}
        />
      </section>
      <Monitor
        w={{ ...w, observables }}
        graphRows={graphRows}
        run={run}
        timeline={timeline}
        scenario={scenario}
        setScenario={setScenario}
        start={runModel}
        setRun={setRun}
        selectedNodeId={selectedId}
        focusNode={focusGraphNode}
      />
      {busy && <div className="busy">ОБРОБКА…</div>}
    </main>
  );
}

function Palette({
  mode,
  w,
  disabled,
}: {
  mode: string;
  w: Workspace;
  disabled: boolean;
}) {
  const blocks = [
    "Start",
    "Event Trigger",
    "Timer",
    "Condition",
    "Python Action",
    "Wait",
    "Resource Operation",
    "Component Command",
    "Metric Check",
    "Manual Command",
    "Parallel Split",
    "Join",
    "Success",
    "Failure",
  ];
  return (
    <aside className="palette">
      <PaneTitle
        small={mode === "model" ? "БАЗА ЕЛЕМЕНТІВ" : "БЛОКИ ПРОЦЕСУ"}
        title={mode === "model" ? "Компоненти" : "Workflow"}
      />
      <input placeholder="Пошук…" />
      <div className="palette-list">
        {(mode === "model"
          ? w.components
          : blocks.map((x) => ({
              id: x.toLowerCase().replaceAll(" ", "_"),
              name: x,
              category: x.toLowerCase().replaceAll(" ", "_"),
            }))
        ).map((c: any) => (
          <button
            disabled={disabled}
            draggable={!disabled}
            onDragStart={(e) => e.dataTransfer.setData(mode, c.id)}
            key={c.id}
          >
            <i style={{ background: palette[c.category] || "#64d8cb" }} />
            <span>
              <b>{c.name}</b>
              <small>
                {mode === "model"
                  ? `${c.level} · ${c.category}`
                  : "scriptable block"}
              </small>
            </span>
            <em>⠿</em>
          </button>
        ))}
      </div>
      <p>
        {disabled
          ? "Published snapshot доступний для запуску й діагностики."
          : "Перетягніть блок на полотно та з’єднайте переходи."}
      </p>
    </aside>
  );
}

function RightPanel({
  run,
  timeline,
  selected,
  selectedEdge,
  component,
  w,
  viewVersion,
  scenario,
  workflow,
  sideTab,
  setSideTab,
  detailTab,
  setDetailTab,
  immutable,
  test,
  setTest,
  mutate,
}: any) {
  const tabs = [
      "element",
      "events",
      "process",
      "repair",
      "resources",
      "control",
      "diagnostics",
    ],
    labels: any = {
      element: "Елемент",
      events: "Події",
      process: "Процес",
      repair: "Ремонт",
      resources: "Ресурси",
      control: "Керування",
      diagnostics: "Діагностика",
    };
  return (
    <aside className="inspector">
      <div className="side-tabs">
        {tabs.map((x) => (
          <button
            className={sideTab === x ? "active" : ""}
            onClick={() => setSideTab(x)}
            key={x}
          >
            {labels[x]}
          </button>
        ))}
      </div>
      {sideTab === "element" && (
        <>
          <PaneTitle
            small="ІНСПЕКТОР"
            title={selected?.name || selectedEdge?.connection_key || "Оберіть вузол або зв’язок"}
          />
          {selectedEdge && <ConnectionInspector edge={selectedEdge} immutable={immutable} mutate={mutate} w={w} version={viewVersion} />}
          {selected && (
            <>
              <div className="tabs">
                {["parameters", "ports", "monitoring", "state", "python", "test"].map((x) => (
                  <button
                    className={detailTab === x ? "active" : ""}
                    onClick={() => setDetailTab(x)}
                    key={x}
                  >
                    {x}
                  </button>
                ))}
              </div>
              {detailTab === "parameters" && (
                selected.component_type_id ? <ParameterForm readOnly={immutable} schema={component?.parameters_schema || {}} value={selected.parameters || {}} save={(parameters) => mutate(() => api.updateNode(selected.id, { parameters }))} /> : <JsonEditor readOnly={immutable} label="Параметри" value={selected.config || {}} save={(config: any) => mutate(() => api.updateWorkflowNode(selected.id, { config }))} />
              )}{" "}
              {detailTab === "ports" && <PortInspector component={component} overrides={selected.port_overrides} />}{" "}
              {detailTab === "monitoring" && <MonitorPicker w={w} version={viewVersion} target={selected} immutable={immutable} mutate={mutate} />}{" "}
              {detailTab === "state" && (
                <JsonEditor
                  readOnly={immutable}
                  label="Початковий стан"
                  value={selected.initial_state || {}}
                  save={(v: any) =>
                    mutate(() =>
                      api.updateNode(selected.id, { initial_state: v }),
                    )
                  }
                />
              )}{" "}
              {detailTab === "python" && (
                <CodeEditor
                  readOnly={immutable}
                  value={selected.python_code || component?.python_code || ""}
                  save={(v: string) =>
                    mutate(() =>
                      selected.component_type_id
                        ? api.updateNode(selected.id, { python_code: v })
                        : api.updateWorkflowNode(selected.id, {
                            python_code: v,
                          }),
                    )
                  }
                />
              )}{" "}
              {detailTab === "test" && (
                <div className="test">
                  <button
                    onClick={async () =>
                      component &&
                      setTest(
                        await api.testComponent(component.id, {
                          python_code: selected.python_code,
                          parameters: selected.parameters,
                          state: selected.initial_state,
                          action: "tick",
                          dt: component.tick_seconds,
                        }),
                      )
                    }
                  >
                    ▶ Один крок
                  </button>
                  {test && <pre>{JSON.stringify(test, null, 2)}</pre>}
                </div>
              )}
              {!immutable && selected.component_type_id && <button className="danger-action" onClick={() => mutate(() => api.deleteNode(selected.id))}>Видалити елемент</button>}
            </>
          )}
        </>
      )}
      {sideTab === "events" && (
        <><EventComposer w={w} scenario={scenario} run={run} target={selected || selectedEdge} targetKind={selectedEdge ? "connection" : "component"} mutate={mutate} /><CepBuilder w={w} scenario={scenario} mutate={mutate} /><EventList events={run?.events || []} timeline={timeline} /></>
      )}{" "}
      {sideTab === "process" && <ProcessState workflow={workflow} run={run} />}{" "}
      {sideTab === "repair" && <WorkOrders rows={run?.work_orders || []} />}{" "}
      {sideTab === "resources" && (
        <Resources
          state={run?.state?.resources}
          transactions={run?.resource_transactions}
        />
      )}{" "}
      {sideTab === "control" && <Commands workflow={workflow} run={run} />}{" "}
      {sideTab === "diagnostics" && (
        <pre>
          {JSON.stringify(
            {
              run: run?.status,
              summary: run?.summary,
              selected: selected && run?.state?.nodes?.[selected.id],
            },
            null,
            2,
          )}
        </pre>
      )}
    </aside>
  );
}

function PortInspector({ component, overrides }: { component: Row; overrides?: Row }) {
  const ports: PortContract[] = component?.ports || [];
  return <div className="contract-list">
    <small>КОНТРАКТ ПОРТІВ · v{component?.version || 1}</small>
    {ports.map((port) => <div className={`contract-port domain-${port.domain.replaceAll(".", "-")}`} key={port.key}>
      <i>{port.direction === "input" ? "→" : port.direction === "output" ? "←" : "↔"}</i>
      <span><b>{overrides?.[port.key]?.name || port.name}</b><small>{port.domain} · {port.quantity}{port.unit ? ` · ${port.unit}` : ""}</small></span>
      {port.required && <em>обов’язковий</em>}
    </div>)}
  </div>;
}

function ConnectionInspector({ edge, immutable, mutate, w, version }: any) {
  return <div className="connection-inspector">
    <div className="connection-route"><b>{edge.source_port}</b><i>→</i><b>{edge.target_port}</b></div>
    <dl><dt>Середовище</dt><dd>{edge.domain || edge.flow_type}</dd><dt>Стан</dt><dd>{edge.enabled === false ? "вимкнено" : "активний"}</dd></dl>
    <JsonEditor readOnly={immutable} label="Властивості зв’язку" value={edge.parameters || {}} save={(parameters) => mutate(() => api.updateEdge(edge.id, { parameters }))} />
    <MonitorPicker w={w} version={version} target={edge} immutable={immutable} mutate={mutate} />
    {!immutable && <div className="connection-actions"><button onClick={() => mutate(() => api.updateEdge(edge.id, { enabled: edge.enabled === false }))}>{edge.enabled === false ? "Увімкнути" : "Вимкнути"}</button><button className="danger-action" onClick={() => mutate(() => api.deleteEdge(edge.id))}>Видалити зв’язок</button></div>}
  </div>;
}

function MonitorPicker({ w, version, target, immutable, mutate }: { w: Workspace; version: Row; target: Row; immutable: boolean; mutate: any }) {
  const available = (w.observables || []).filter((item) => item.target_id === target.id),
    [selected, setSelected] = useState("");
  useEffect(() => setSelected(available[0]?.address || ""), [target.id]);
  const add = () => {
    const observable = available.find((item) => item.address === selected);
    if (!observable) return;
    const current = (w.monitors || []).find((item) => item.model_version_id === version.id);
    const series = { address: observable.address, name: observable.name, unit: observable.unit, style: "line", color: seriesColors[(current?.panels?.[0]?.series?.length || 0) % seriesColors.length] };
    if (!current) return mutate(() => api.createMonitor(version.id, { name: "Монітор моделі", panels: [{ id: "main", name: "Основні показники", type: "chart", series: [series] }] }));
    const panels = current.panels?.length ? current.panels.map((panel: Row, index: number) => index ? panel : { ...panel, series: [...(panel.series || []).filter((item: Row) => item.address !== series.address), series] }) : [{ id: "main", name: "Основні показники", type: "chart", series: [series] }];
    return mutate(() => api.updateMonitor(current.id, { panels }));
  };
  return <div className="monitor-picker">
    <small>ДОСТУПНІ ПОКАЗНИКИ · визначені моделлю</small>
    {!available.length ? <p>Цей елемент поки не публікує показників.</p> : <>
      <select value={selected} onChange={(event) => setSelected(event.target.value)}>{available.map((item) => <option value={item.address} key={item.address}>{item.name}{item.unit ? ` · ${item.unit}` : ""}</option>)}</select>
      <button disabled={immutable} onClick={add}>＋ Додати до моніторингу</button>
      {immutable && <p>Створіть draft-копію моделі, щоб змінити шаблон моніторингу.</p>}
    </>}
  </div>;
}

function EventComposer({ w, scenario, run, target, targetKind, mutate }: any) {
  const definitions = (w.event_types || []).filter((item: Row) => !target || !item.target_kinds?.length || item.target_kinds.includes(targetKind)),
    [eventType, setEventType] = useState("");
  useEffect(() => setEventType(definitions[0]?.id || ""), [target?.id, targetKind, w.event_types?.length]);
  if (!target) return <div className="event-composer"><small>НОВА ПОДІЯ</small><p>Оберіть елемент або зв’язок на схемі, щоб створити подію з правильною ціллю.</p></div>;
  const submit = () => {
    if (!eventType) return;
    const body = { event_type: eventType, target: { kind: targetKind, id: target.id, key: target.instance_key || target.connection_key || target.id }, payload: {}, title: definitions.find((item: Row) => item.id === eventType)?.name || eventType };
    return mutate(() => run?.id ? api.inject(run.id, body) : api.createScenarioEvent(scenario, { ...body, offset_seconds: 0 }));
  };
  return <div className="event-composer"><small>НОВА ТИПІЗОВАНА ПОДІЯ</small><b>{target.name || target.connection_key}</b><select value={eventType} onChange={(event) => setEventType(event.target.value)}>{definitions.map((item: Row) => <option value={item.id} key={item.id}>{item.name}</option>)}</select><button disabled={!eventType} onClick={submit}>{run?.id ? "Додати до run" : "Додати до сценарію"}</button></div>;
}

function CepBuilder({ w, scenario, mutate }: any) {
  const numeric = (w.observables || []).filter((item: Row) => item.value_type === "number"),
    [operator, setOperator] = useState("compare"), [observable, setObservable] = useState(numeric[0]?.address || "system:frequency_hz"),
    [comparison, setComparison] = useState("lt"), [value, setValue] = useState(49.5), [windowSeconds, setWindowSeconds] = useState(30),
    [eventTypes, setEventTypes] = useState("line_fault, trip"), [emit, setEmit] = useState((w.event_types || [])[0]?.id || "alert");
  const save = () => {
    const metric = { operator: "compare", observable, comparison, value, hysteresis: 0.02 }, event = { operator: "event", event_type: eventTypes.split(",")[0].trim(), window_seconds: windowSeconds };
    let condition: Row = metric;
    if (["average", "min", "max", "trend"].includes(operator)) condition = { operator, observable, comparison, value, window_seconds: windowSeconds };
    else if (operator === "duration") condition = { operator, seconds: windowSeconds, condition: metric };
    else if (operator === "absence") condition = { operator, window_seconds: windowSeconds, condition: event };
    else if (operator === "sequence") condition = { operator, event_types: eventTypes.split(",").map((item) => item.trim()).filter(Boolean), window_seconds: windowSeconds };
    else if (operator === "count") condition = { operator, condition: event, comparison, value, window_seconds: windowSeconds };
    else if (["all", "any"].includes(operator)) condition = { operator, conditions: [metric, event] };
    else if (operator === "not") condition = { operator, condition: metric };
    return mutate(() => api.createCepRule(scenario, { name: `${operator} → ${emit}`, condition, emit: { event_type: emit, payload: {} } }));
  };
  return <details className="cep-builder"><summary>＋ Правило автоматичного виявлення (CEP)</summary><div><label>Умова<select value={operator} onChange={(event) => setOperator(event.target.value)}>{["compare", "all", "any", "not", "sequence", "count", "average", "min", "max", "duration", "absence", "trend"].map((item) => <option key={item}>{item}</option>)}</select></label>{!["sequence", "absence"].includes(operator) && <label>Показник<select value={observable} onChange={(event) => setObservable(event.target.value)}>{numeric.map((item: Row) => <option value={item.address} key={item.address}>{item.target_name} · {item.name}</option>)}</select></label>}<label>Порівняння<select value={comparison} onChange={(event) => setComparison(event.target.value)}>{["lt", "lte", "gt", "gte", "eq", "ne"].map((item) => <option key={item}>{item}</option>)}</select></label><label>Значення<input type="number" value={value} onChange={(event) => setValue(Number(event.target.value))} /></label><label>Вікно / тривалість, с<input type="number" value={windowSeconds} onChange={(event) => setWindowSeconds(Number(event.target.value))} /></label><label>Послідовність подій<input value={eventTypes} onChange={(event) => setEventTypes(event.target.value)} /></label><label>Створити подію<select value={emit} onChange={(event) => setEmit(event.target.value)}>{(w.event_types || []).map((item: Row) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><button onClick={save}>Зберегти правило</button></div></details>;
}

function EventList({
  events,
  timeline,
}: {
  events: Row[];
  timeline: Row | null;
}) {
  const [view, setView] = useState<"programmed" | "monitor">("monitor"),
    timelineStart = timeline?.start || new Date().toISOString();
  const templates: Row[] = (timeline?.events || []).map((e: Row) => ({
    ...e,
    scheduled_at: new Date(
      new Date(timelineStart).getTime() + e.offset_seconds * 1000,
    ).toISOString(),
    status: "programmed",
    payload: {
      ...e.payload,
      _phase: e.phase,
      _title: e.title,
      _evidence: e.evidence_kind,
    },
  }));
  const programmed: Row[] = events.length ? events : templates,
    processed: Row[] = events
      .filter((e: Row) => e.status === "processed")
      .sort(
        (a: Row, b: Row) =>
          new Date(b.scheduled_at).getTime() -
          new Date(a.scheduled_at).getTime(),
      ),
    rows: Row[] = view === "monitor" ? processed : programmed;
  return (
    <div className="side-list">
      <PaneTitle
        small={view === "monitor" ? "ФАКТИЧНИЙ ЖУРНАЛ" : "КАЛЕНДАР"}
        title={
          view === "monitor"
            ? `Монітор · ${processed.length}`
            : `Запрограмовано · ${programmed.length}`
        }
      />
      <div className="event-mode">
        <button
          className={view === "programmed" ? "active" : ""}
          onClick={() => setView("programmed")}
        >
          Запрограмовані
        </button>
        <button
          className={view === "monitor" ? "active" : ""}
          onClick={() => setView("monitor")}
        >
          Монітор подій
        </button>
      </div>
      {!rows.length && (
        <p>
          {view === "monitor"
            ? "Виконані події з’являтимуться тут, найновіші — зверху."
            : "Події не запрограмовані."}
        </p>
      )}
      {rows.map((e: Row) => (
        <article key={e.id}>
          <time>{clock(e.scheduled_at)}</time>
          <b>{e.payload?._title || e.event_type}</b>
          <span>
            {e.payload?._phase || e.origin} ·{" "}
            {e.payload?._evidence || "derived"}
          </span>
          <em className={e.status}>{e.status}</em>
        </article>
      ))}
    </div>
  );
}
function ProcessState({
  workflow,
  run,
}: {
  workflow: Row | null;
  run: Row | null;
}) {
  return (
    <div className="side-list">
      <PaneTitle
        small="WORKFLOW"
        title={workflow?.version?.name || "Не підключено"}
      />
      {workflow?.nodes?.map((n: Row) => (
        <article
          key={n.id}
          className={
            run?.workflow_instances?.[0]?.current_node_id === n.id
              ? "current"
              : ""
          }
        >
          <b>{n.name}</b>
          <span>
            {n.block_type} · {n.config?.event_type}
          </span>
        </article>
      ))}
    </div>
  );
}
function WorkOrders({ rows }: { rows: Row[] }) {
  return (
    <div className="side-list">
      <PaneTitle small="WORK ORDERS" title={`${rows.length} заявок`} />
      {rows.map((x) => (
        <article key={x.id}>
          <b>{x.result?.logical_id || x.node_id}</b>
          <span>
            {x.status} · ремонт {x.repair_hours || 0} год
          </span>
          <em>{x.completed_at ? "закрито" : "активна"}</em>
        </article>
      ))}
    </div>
  );
}
function Resources({
  state,
  transactions,
}: {
  state: any;
  transactions: Row[];
}) {
  return (
    <div className="side-list">
      <PaneTitle small="RESOURCE LEDGER" title="Ресурси" />
      {Object.entries(state || {}).map(([id, x]: any) => (
        <article key={id}>
          <b>{id}</b>
          <span>
            доступно {x.available} · резерв {x.reserved} {x.unit}
          </span>
        </article>
      ))}
      {transactions?.map((x) => (
        <article key={x.id}>
          <time>{clock(x.model_time)}</time>
          <b>
            {x.operation} · {x.resource_id}
          </b>
          <span>
            {x.quantity} {x.unit}
          </span>
        </article>
      ))}
    </div>
  );
}
function Commands({
  workflow,
  run,
}: {
  workflow: Row | null;
  run: Row | null;
}) {
  const [message, setMessage] = useState("");
  const commands = workflow?.version?.settings?.commands || [];
  return (
    <div className="side-list">
      <PaneTitle small="SCRIPT COMMANDS" title="Керування" />
      {commands.map((c: Row) => (
        <article key={c.id}>
          <b>{c.label}</b>
          <span>{Object.keys(c.parameters || {}).join(", ")}</span>
          <button
            disabled={!run}
            onClick={async () => {
              if (!run) return;
              const result = await api.userCommand(run.id, {
                command_type: c.id,
                payload: { quantity: 2 },
              });
              setMessage(`${c.label}: ${result.status}`);
            }}
          >
            Виконати
          </button>
        </article>
      ))}
      <p>{message || "Команди оголошуються workflow-скриптом."}</p>
    </div>
  );
}

const speedPresets = [
  { value: 1, label: "1 секунда / сек" },
  { value: 60, label: "1 хвилина / сек" },
  { value: 3600, label: "1 година / сек" },
  { value: 86400, label: "1 день / сек" },
  { value: 2592000, label: "1 місяць / сек" },
  { value: 31536000, label: "1 рік / сек" },
];
function SpeedSelect({
  value,
  setValue,
  label,
}: {
  value: number;
  setValue: (n: number) => void;
  label: string;
}) {
  const preset = speedPresets.some((x) => x.value === value),
    [custom, setCustom] = useState(preset ? 30 : value / 60),
    [unit, setUnit] = useState(60);
  return (
    <label className="speed-select">
      <span>{label}</span>
      <select
        value={preset ? String(value) : "custom"}
        onChange={(e) => {
          if (e.target.value !== "custom") setValue(Number(e.target.value));
          else setValue(custom * unit);
        }}
      >
        {speedPresets.map((x) => (
          <option value={x.value} key={x.value}>
            {x.label}
          </option>
        ))}
        <option value="custom">Власна швидкість…</option>
      </select>
      {!preset && (
        <span className="custom-speed">
          <input
            type="number"
            min="0.001"
            step="any"
            value={custom}
            onChange={(e) => {
              const n = Math.max(0.001, Number(e.target.value));
              setCustom(n);
              setValue(n * unit);
            }}
          />
          <select
            value={unit}
            onChange={(e) => {
              const u = Number(e.target.value);
              setUnit(u);
              setValue(custom * u);
            }}
          >
            <option value="1">сек / сек</option>
            <option value="60">хв / сек</option>
            <option value="3600">год / сек</option>
            <option value="86400">днів / сек</option>
          </select>
        </span>
      )}
    </label>
  );
}
function Monitor({
  w,
  graphRows,
  run,
  timeline,
  scenario,
  setScenario,
  start,
  setRun,
  selectedNodeId,
  focusNode,
}: any) {
  const [idleSpeed, setIdleSpeed] = useState(3600),
    [eventSpeed, setEventSpeed] = useState(60),
    [eventDuration, setEventDuration] = useState(10),
    [eventTypes, setEventTypes] = useState<string[]>([
      "line_fault",
      "repair_completed",
      "restoration_complete",
    ]),
    [scrubMs, setScrubMs] = useState<number | null>(null),
    [settingsOpen, setSettingsOpen] = useState(false);
  const cmd = async (action: string, body: Row = {}) =>
    run && setRun(await api.command(run.id, { action, ...body }));
  const events = run?.events?.length
    ? run.events
    : (timeline?.events || []).map((e: Row) => ({
        ...e,
        scheduled_at: new Date(
          new Date(timeline.start).getTime() + e.offset_seconds * 1000,
        ).toISOString(),
        status: "template",
        payload: {
          _phase: e.phase,
          _title: e.title,
          _evidence: e.evidence_kind,
        },
      }));
  const startMs = new Date(
      timeline?.start || run?.current_time || Date.now(),
    ).getTime(),
    endMs = new Date(
      timeline?.end || run?.end_time || Date.now() + 1,
    ).getTime(),
    currentMs = new Date(
      run?.current_time || timeline?.start || Date.now(),
    ).getTime(),
    shownMs = scrubMs ?? currentMs,
    incidentMs = new Date(
      timeline?.incident || run?.incident_at || currentMs,
    ).getTime(),
    metrics = run?.summary || {};
  const definitions = w.metrics.filter((m: Row) =>
      [
        "generation_mw",
        "demand_mw",
        "unserved_mw",
        "frequency_hz",
        "voltage_pu",
        "gas_consumption_mw",
        "gas_remaining_mwh",
        "co2_tph",
      ].includes(m.id),
    ),
    flows = run?.flows || [],
    availableTypes = Array.from(
      new Set((timeline?.events || []).map((e: Row) => e.event_type)),
    ) as string[];
  const settings = {
    idle_speed: idleSpeed,
    event_speed: eventSpeed,
    event_speed_duration_seconds: eventDuration,
    event_speed_event_types: eventTypes,
  };
  const applySettings = async () => {
    if (run)
      setRun(
        await api.command(run.id, { action: "playback_settings", ...settings }),
      );
  };
  useEffect(() => {
    if (!run || scrubMs === null) return;
    const timer = window.setTimeout(async () => {
      try {
        setRun(await api.seek(run.id, { at: new Date(scrubMs).toISOString() }));
      } finally {
        setScrubMs(null);
      }
    }, 450);
    return () => window.clearTimeout(timer);
  }, [scrubMs, run?.id]);
  return (
    <section className="console">
      <div className="transport">
        <select value={scenario} onChange={(e) => setScenario(e.target.value)}>
          {w.scenarios.map((s: Row) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
        <div className="transport-buttons">
          <button className="start" onClick={() => start(settings)}>
            ▶ Start
          </button>
          {["pause", "step", "resume", "stop"].map((x) => (
            <button disabled={!run} onClick={() => cmd(x)} key={x}>
              {x}
            </button>
          ))}
          <button
            className={settingsOpen ? "active" : ""}
            onClick={() => setSettingsOpen(!settingsOpen)}
          >
            ⚙ Швидкості
          </button>
        </div>
      </div>
      <div className="clock">
        <small>МОДЕЛЬНИЙ ЧАС · EUROPE/KYIV</small>
        <b>{clock(run?.current_time || timeline?.start)}</b>
        <span>
          {run?.status || "готовий"} · базова {run?.idle_speed || idleSpeed}× ·
          подієва {run?.event_speed || eventSpeed}×
        </span>
      </div>
      <div className="metric-grid">
        {definitions.map((m: Row) => (
          <span key={m.id}>
            <small>{m.name}</small>
            <b>
              {metrics[m.id] ?? "—"} {m.unit}
            </b>
          </span>
        ))}
      </div>
      {settingsOpen && (
        <div className="playback-settings">
          <button
            className="playback-close"
            type="button"
            aria-label="Закрити налаштування швидкостей"
            title="Закрити"
            onClick={() => setSettingsOpen(false)}
          >
            ×
          </button>
          <SpeedSelect
            label="Без подій"
            value={idleSpeed}
            setValue={setIdleSpeed}
          />
          <SpeedSelect
            label="Під час події"
            value={eventSpeed}
            setValue={setEventSpeed}
          />
          <label>
            <span>Тривалість подієвої швидкості</span>
            <input
              type="number"
              min="0"
              value={eventDuration}
              onChange={(e) => setEventDuration(Number(e.target.value))}
            />
            <small>секунд реального часу</small>
          </label>
          <div className="event-triggers">
            <span>Події-тригери</span>
            {availableTypes.map((type) => (
              <label key={type}>
                <input
                  type="checkbox"
                  checked={eventTypes.includes(type)}
                  onChange={() =>
                    setEventTypes((old) =>
                      old.includes(type)
                        ? old.filter((x) => x !== type)
                        : [...old, type],
                    )
                  }
                />
                {type}
              </label>
            ))}
          </div>
          <button onClick={applySettings} disabled={!run}>
            Застосувати до run
          </button>
        </div>
      )}
      <div className="timeline">
        <div className="timeline-head">
          <b>{clock(timeline?.start)}</b>
          <span>ІНЦИДЕНТ · {clock(timeline?.incident)}</span>
          <b>{clock(timeline?.end)}</b>
        </div>
        <div className="rail">
          <i
            className="incident-marker"
            style={{ left: `${pct(incidentMs, startMs, endMs)}%` }}
          />
          {events.map((e: Row, i: number) => (
            <button
              key={e.id || i}
              className={`event-dot ${e.payload?._phase || "scenario"} ${e.status}`}
              style={{
                left: `${pct(new Date(e.scheduled_at).getTime(), startMs, endMs)}%`,
              }}
              title={`${clock(e.scheduled_at)} · ${e.payload?._title || e.event_type}`}
            />
          ))}
          <input
            aria-label="Поточний модельний час"
            className="timeline-scrubber"
            type="range"
            min={startMs}
            max={endMs}
            step={60000}
            value={shownMs}
            disabled={!run}
            onChange={(e) => setScrubMs(Number(e.target.value))}
          />
        </div>
        <div className="timeline-labels">
          <span>T−24 год</span>
          <strong>
            {scrubMs !== null
              ? `Перейти: ${clock(new Date(scrubMs).toISOString())}`
              : `${Math.round(pct(currentMs, startMs, endMs))}%`}
          </strong>
          <span>кінець</span>
        </div>
      </div>
      <div className="energy-monitor">
        <b>ПЕРЕХІД ЕНЕРГІЇ</b>
        <div className="energy-chain">
          <span>
            Газ <em>{metrics.gas_consumption_mw ?? 0} MWth</em>
          </span>
          <i>→</i>
          <span>
            Генерація <em>{metrics.generation_mw ?? 0} MW</em>
          </span>
          <i>→</i>
          <span>
            Споживання <em>{metrics.served_load_mw ?? 0} MW</em>
          </span>
          <i>→</i>
          <span>
            Тепло / світло{" "}
            <em>
              {metrics.heat_mw ?? 0} / {metrics.visible_radiation_mw ?? 0} MW
            </em>
          </span>
        </div>
        <div className="flow-strip">
          {flows.slice(0, 8).map((f: Row) => (
            <span key={f.id}>
              {f.flow_type} · {Number(f.value).toFixed(1)} {f.unit}
            </span>
          ))}
        </div>
      </div>
      <DiagnosticCharts
        w={w}
        nodes={graphRows}
        samples={(run?.samples || []).slice().reverse()}
        timeline={timeline}
        selectedNodeId={selectedNodeId}
        focusNode={focusNode}
      />
    </section>
  );
}

const seriesColors = ["#f0bd63", "#b7f34a", "#64d8cb", "#d899ff", "#ff8f72"];

function DiagnosticCharts({ w, nodes, samples, timeline, selectedNodeId, focusNode }: any) {
  const dashboard = w.dashboards.find((item: Row) => item.id === "energy-system-monitor"),
    configured = dashboard?.panels?.find((panel: Row) => panel.type === "diagnostic_charts")?.sets || [],
    [sets, setSets] = useState<Row[]>(configured),
    [active, setActive] = useState(0),
    [point, setPoint] = useState(nodes[0]?.id || ""),
    [metric, setMetric] = useState(""),
    [style, setStyle] = useState("line"),
    [fromPct, setFromPct] = useState(0),
    [toPct, setToPct] = useState(100),
    [saved, setSaved] = useState("");
  useEffect(() => {
    setSets(configured);
    setActive(0);
    setFromPct(0);
    setToPct(100);
  }, [dashboard?.id, nodes?.[0]?.model_version_id]);
  const catalog = (w.observables || []).filter((item: Row) => item.scope === "component"),
    controlPoints = nodes.filter((node: Row) => catalog.some((item: Row) => item.target_id === node.id)).map((node: Row) => ({ type: node.id, node })),
    pointMetrics = catalog.filter((item: Row) => item.target_id === point && item.value_type === "number"),
    current = sets[Math.min(active, Math.max(sets.length - 1, 0))],
    fullStart = new Date(timeline?.start || samples[0]?.model_time || Date.now()).getTime(),
    fullEnd = new Date(timeline?.end || samples.at(-1)?.model_time || fullStart + 1).getTime(),
    timeMin = fullStart + (Math.max(0, fromPct) / 100) * Math.max(1, fullEnd - fullStart),
    timeMax = fullStart + (Math.min(100, toPct) / 100) * Math.max(1, fullEnd - fullStart),
    rangeSamples = samples.filter((sample: Row) => {
      const time = new Date(sample.model_time).getTime();
      return time >= timeMin && time <= timeMax;
    }),
    preceding = samples.filter((sample: Row) => new Date(sample.model_time).getTime() < timeMin).at(-1),
    visible = preceding ? [{ ...preceding, model_time: new Date(timeMin).toISOString() }, ...rangeSamples] : rangeSamples,
    incidentAt = timeline?.incident,
    metricSpec = (seriesOrId: Row | string) => {
      const series = typeof seriesOrId === "string" ? { metric: seriesOrId } : seriesOrId;
      const observable = catalog.find((item: Row) => item.address === series.address) || catalog.find((item: Row) => item.target_id === series.target_id && item.metric_key === (series.metric_key || series.metric));
      const legacy = w.metrics.find((item: Row) => item.id === (series.metric_key || series.metric));
      return observable ? { id: observable.metric_key, label: observable.name, unit: observable.unit } : legacy ? { id: legacy.id, label: legacy.name, unit: legacy.unit } : undefined;
    },
    valueAt = (sample: Row, series: Row) =>
      diagnosticSeriesValue(sample, nodes, series),
    domain = (series: Row) => {
      const values = visible.map((sample: Row) => valueAt(sample, series)).filter(Number.isFinite);
      if ((series.metric_key || series.metric) === "voltage_pu") return [0, 1.1];
      if ((series.metric_key || series.metric) === "frequency_hz") return [0, 51];
      return [Math.min(0, ...values), Math.max(1, ...values) * 1.08];
    },
    x = (sample: Row) => 48 + ((new Date(sample.model_time).getTime() - timeMin) / Math.max(1, timeMax - timeMin)) * 824,
    y = (value: number, series: Row) => {
      const [min, max] = domain(series);
      return 186 - ((value - min) / Math.max(.0001, max - min)) * 150;
    },
    linePath = (series: Row) => {
      const points = visible.map((sample: Row) => ({
        x: x(sample),
        y: y(valueAt(sample, series), series),
      })).filter((point: Row) => Number.isFinite(point.y));
      if (!points.length) return "";
      const first = `M${points[0].x},${points[0].y}`;
      if (["voltage_pu", "frequency_hz"].includes(series.metric_key || series.metric)) {
        return points.slice(1).reduce(
          (path: string, point: Row) => `${path} H${point.x} V${point.y}`,
          first,
        );
      }
      return points.slice(1).reduce(
        (path: string, point: Row) => `${path} L${point.x},${point.y}`,
        first,
      );
    };
  useEffect(() => {
    const nextPoint = preferredDiagnosticPoint(nodes, catalog, selectedNodeId, point);
    if (nextPoint !== point) setPoint(nextPoint);
    if (!pointMetrics.some((item: Row) => item.address === metric)) setMetric(pointMetrics[0]?.address || "");
  }, [catalog.length, point, metric, nodes.length, selectedNodeId]);
  const updateCurrent = (next: Row) => setSets((old) => old.map((item, index) => index === active ? next : item));
  const addSeries = () => {
    if (!current) return;
    const observable = pointMetrics.find((item: Row) => item.address === metric) || pointMetrics[0];
    if (!observable) return;
    updateCurrent({
      ...current,
      series: [...current.series, { target_id: point, target_key: observable.target_key, address: observable.address, metric_key: observable.metric_key, style, color: seriesColors[current.series.length % seriesColors.length] }],
    });
  };
  const addSet = () => {
    const next = { id: `chart-${Date.now()}`, name: `Набір ${sets.length + 1}`, series: [] };
    setSets((old) => [...old, next]); setActive(sets.length);
  };
  const save = async () => {
    if (!dashboard) return;
    const panels = dashboard.panels.map((panel: Row) => panel.type === "diagnostic_charts" ? { ...panel, sets } : panel);
    await api.updateDashboard(dashboard.id, { panels });
    setSaved("Збережено"); window.setTimeout(() => setSaved(""), 1600);
  };
  const focusIncident = () => {
    if (!incidentAt) return;
    const incident = new Date(incidentAt).getTime();
    const center = ((incident - fullStart) / Math.max(1, fullEnd - fullStart)) * 100;
    const span = Math.max(.25, (12 * 3600 * 1000 / Math.max(1, fullEnd - fullStart)) * 100);
    setFromPct(Math.max(0, center - span)); setToPct(Math.min(100, center + span));
  };
  if (!current) return <div className="diagnostic-charts"><small>ГРАФІКИ · немає конфігурації</small></div>;
  return (
    <div className="diagnostic-charts">
      <div className="chart-tabs">
        {sets.map((item, index) => <button className={index === active ? "active" : ""} onClick={() => setActive(index)} key={item.id}>{item.name}</button>)}
        <button onClick={addSet} title="Новий комплект графіків">＋</button>
      </div>
      <div className="chart-config">
        <select aria-label="Точка діагностики" value={point} onChange={(e) => { const id = e.target.value; setPoint(id); setMetric(catalog.find((item: Row) => item.target_id === id && item.value_type === "number")?.address || ""); focusNode(id); }}>
          {controlPoints.map(({ type, node }: any) => <option value={type} key={type}>{node.name}</option>)}
        </select>
        <select aria-label="Параметр діагностики" value={metric} onChange={(e) => setMetric(e.target.value)}>
          {pointMetrics.map((item: Row) => <option value={item.address} key={item.address}>{item.name}{item.unit ? ` · ${item.unit}` : ""}</option>)}
        </select>
        <select aria-label="Тип графіка" value={style} onChange={(e) => setStyle(e.target.value)}><option value="line">Лінія</option><option value="bar">Стовпчики</option></select>
        <button onClick={addSeries}>＋ Ряд</button><button onClick={save}>Зберегти</button><em>{saved}</em>
      </div>
      <div className="series-legend">
        {current.series.map((series: Row, index: number) => {
          const nodeId = resolveSeriesNodeId(nodes, series);
          const node = nodes.find((item: Row) => item.id === nodeId);
          const spec = metricSpec(series);
          const stats = diagnosticSeriesStats(visible, nodes, series);
          const unit = spec?.unit ? ` ${spec.unit}` : "";
          return <span className="series-chip" key={`${series.address || series.point_component_type}-${series.metric_key || series.metric}-${index}`} style={{ "--series": series.color } as any}>
            <button className="series-summary" onClick={() => nodeId && focusNode(nodeId)} title="Показати елемент на схемі">
              <span><i />{node?.name || series.target_key || series.point_component_type} · {spec?.label || series.metric_key || series.metric}</span>
              <strong>{stats ? `${formatDiagnosticValue(stats.latest)}${unit}` : "немає даних"}</strong>
              {stats && <small>min {formatDiagnosticValue(stats.min)} · max {formatDiagnosticValue(stats.max)}{unit} · {stats.count} вим.</small>}
            </button>
            <button className="remove-series" aria-label="Прибрати ряд" title="Прибрати ряд" onClick={() => updateCurrent({ ...current, series: current.series.filter((_: Row, i: number) => i !== index) })}>×</button>
          </span>;
        })}
      </div>
      <div className="chart-canvas">
        {!visible.length ? <p>Запустіть модель, щоб накопичити історичні вимірювання.</p> : <svg viewBox="0 0 900 220" role="img" aria-label={`Діагностичний графік ${current.name}`}>
          {[36, 86, 136, 186].map((top) => <line key={top} x1="48" x2="872" y1={top} y2={top} className="grid-line" />)}
          {incidentAt && new Date(incidentAt).getTime() >= timeMin && new Date(incidentAt).getTime() <= timeMax && <><line x1={x({model_time:incidentAt})} x2={x({model_time:incidentAt})} y1="24" y2="190" className="incident-line"/><text x={x({model_time:incidentAt}) + 5} y="30">АВАРІЯ</text></>}
          {current.series.map((series: Row, seriesIndex: number) => series.style === "bar" ? visible.map((sample: Row, index: number) => {
            const value = valueAt(sample, series), width = Math.max(2, 760 / Math.max(visible.length, 1) / Math.max(current.series.length, 1));
            if (!Number.isFinite(value)) return null;
            return <rect key={`${seriesIndex}-${index}`} x={x(sample) - width / 2 + seriesIndex * 2} y={y(value, series)} width={width} height={Math.max(1, 186 - y(value, series))} fill={series.color} opacity=".42"><title>{clock(sample.model_time)} · {value} {metricSpec(series)?.unit}</title></rect>;
          }) : <path key={seriesIndex} d={linePath(series)} fill="none" stroke={series.color} strokeWidth="3" strokeDasharray={diagnosticSeriesDash(seriesIndex)} strokeLinecap="round" strokeLinejoin="round"><title>{metricSpec(series)?.label}</title></path>)}
          <text x="48" y="210">{clock(visible[0]?.model_time)}</text><text x="872" y="210" textAnchor="end">{clock(visible.at(-1)?.model_time)}</text>
        </svg>}
      </div>
      <div className="chart-zoom"><span>Масштаб часу</span><input aria-label="Початок ділянки" type="range" min="0" max="99" step="0.1" value={fromPct} onChange={(e) => setFromPct(Math.min(Number(e.target.value), toPct - .1))}/><input aria-label="Кінець ділянки" type="range" min="1" max="100" step="0.1" value={toPct} onChange={(e) => setToPct(Math.max(Number(e.target.value), fromPct + .1))}/><button onClick={focusIncident}>Аварія ±12 год</button><button onClick={() => { setFromPct(0); setToPct(100); }}>Весь час</button></div>
    </div>
  );
}

function PaneTitle({ small, title }: { small: string; title: string }) {
  return (
    <div className="pane-title">
      <small>{small}</small>
      <b>{title}</b>
    </div>
  );
}
function JsonEditor({
  label,
  value,
  save,
  readOnly = false,
}: {
  label: string;
  value: any;
  save: (v: any) => void;
  readOnly?: boolean;
}) {
  const [text, setText] = useState(JSON.stringify(value, null, 2));
  useEffect(() => setText(JSON.stringify(value, null, 2)), [value]);
  return (
    <label className="editor">
      <span>{label}</span>
      <textarea
        readOnly={readOnly}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      {!readOnly && (
        <button
          onClick={() => {
            try {
              save(JSON.parse(text));
            } catch {
              alert("Некоректний JSON");
            }
          }}
        >
          Зберегти
        </button>
      )}
    </label>
  );
}
function ParameterForm({ schema, value, save, readOnly }: { schema: Row; value: Row; save: (value: Row) => void; readOnly: boolean }) {
  const [draft, setDraft] = useState<Row>(value);
  useEffect(() => setDraft(value), [value]);
  const fields = [...new Set([...Object.keys(schema || {}), ...Object.keys(value || {})])];
  return <div className="parameter-form"><small>СТРУКТУРОВАНІ ПАРАМЕТРИ</small>{fields.map((key) => {
    const current = draft[key] ?? schema[key], type = typeof current;
    if (type === "boolean") return <label key={key}><span>{key.replaceAll("_", " ")}</span><input type="checkbox" checked={Boolean(current)} disabled={readOnly} onChange={(event) => setDraft({ ...draft, [key]: event.target.checked })} /></label>;
    if (type === "number") return <label key={key}><span>{key.replaceAll("_", " ")}</span><input type="number" value={current ?? ""} disabled={readOnly} onChange={(event) => setDraft({ ...draft, [key]: Number(event.target.value) })} /></label>;
    if (type === "string") return <label key={key}><span>{key.replaceAll("_", " ")}</span><input value={current ?? ""} disabled={readOnly} onChange={(event) => setDraft({ ...draft, [key]: event.target.value })} /></label>;
    return null;
  })}{!readOnly && <button onClick={() => save(draft)}>Зберегти параметри</button>}<details><summary>Розширений JSON</summary><pre>{JSON.stringify(draft, null, 2)}</pre></details></div>;
}
function CodeEditor({
  value,
  save,
  readOnly = false,
}: {
  value: string;
  save: (v: string) => void;
  readOnly?: boolean;
}) {
  const [text, setText] = useState(value);
  useEffect(() => setText(value), [value]);
  return (
    <label className="editor code">
      <span>Локальна поведінка Python · advanced</span>
      <textarea
        readOnly={readOnly}
        spellCheck={false}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      {!readOnly && <button onClick={() => save(text)}>Зберегти Python</button>}
    </label>
  );
}
