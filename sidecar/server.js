/**
 * CombinePro memory sidecar.
 *
 * Thin Express REST wrapper around @vonneollc/knbase's programmatic API so the
 * Python orchestrator can read/write governance memory over localhost HTTP.
 * One sidecar instance serves one project root (set via POST /init or
 * POST /session/start).
 */
import express from "express";
import {
  openProject,
  initProject,
  startSession,
  getContext,
  writeGovernanceFile,
  beginTask,
  completeTask,
  getStatus,
  appendLog,
  readLog,
} from "@vonneollc/knbase";

const PORT = Number(process.env.SIDECAR_PORT ?? process.env.PORT ?? 8787);

const app = express();
app.use(express.json({ limit: "2mb" }));

// Module state: the single project this sidecar instance serves.
let projectRoot = null;

function requireProject(res) {
  if (!projectRoot) {
    res.status(409).json({ ok: false, error: "No project initialized. POST /init first." });
    return null;
  }
  try {
    return openProject(projectRoot);
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err?.message ?? err) });
    return null;
  }
}

// Wrap a handler so knbase exceptions become JSON errors instead of crashes.
const guard = (fn) => async (req, res) => {
  try {
    await fn(req, res);
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err?.message ?? err) });
  }
};

app.get("/health", (_req, res) => {
  res.json({ ok: true, service: "combinepro-sidecar", projectRoot });
});

app.post(
  "/init",
  guard((req, res) => {
    const { root, docsDir } = req.body ?? {};
    if (!root) {
      return res.status(400).json({ ok: false, error: "Missing 'root' in body" });
    }
    const result = initProject(root, docsDir);
    projectRoot = result.root;
    res.json({ ok: true, ...result });
  }),
);

app.post(
  "/session/start",
  guard((req, res) => {
    const root = req.body?.root ?? projectRoot;
    if (!root) {
      return res.status(400).json({ ok: false, error: "Missing 'root' (no project initialized)" });
    }
    const project = openProject(root);
    projectRoot = project.root;
    res.json({ ok: true, ...startSession(project) });
  }),
);

app.get(
  "/context",
  guard((req, res) => {
    const project = requireProject(res);
    if (!project) return;
    const files = req.query.files ? String(req.query.files).split(",") : undefined;
    const full = req.query.full === "1" || req.query.full === "true";
    res.json({ ok: true, ...getContext(project, files, full) });
  }),
);

app.post(
  "/governance/:key",
  guard((req, res) => {
    const project = requireProject(res);
    if (!project) return;
    const { content, summary } = req.body ?? {};
    if (typeof content !== "string" || typeof summary !== "string") {
      return res.status(400).json({ ok: false, error: "Body needs string 'content' and 'summary'" });
    }
    const result = writeGovernanceFile(project, req.params.key, content, summary);
    res.status(result.ok ? 200 : 422).json(result);
  }),
);

app.post(
  "/task/begin",
  guard((req, res) => {
    const project = requireProject(res);
    if (!project) return;
    const { description } = req.body ?? {};
    if (typeof description !== "string" || !description.trim()) {
      return res.status(400).json({ ok: false, error: "Body needs non-empty 'description'" });
    }
    const result = beginTask(project, description);
    res.status(result.ok ? 200 : 409).json(result);
  }),
);

app.post(
  "/task/complete",
  guard((req, res) => {
    const project = requireProject(res);
    if (!project) return;
    const { taskId, summary } = req.body ?? {};
    if (typeof taskId !== "string" || typeof summary !== "string") {
      return res.status(400).json({ ok: false, error: "Body needs string 'taskId' and 'summary'" });
    }
    const result = completeTask(project, taskId, summary);
    res.status(result.ok ? 200 : 409).json(result);
  }),
);

app.get(
  "/status",
  guard((_req, res) => {
    const project = requireProject(res);
    if (!project) return;
    res.json({ ok: true, ...getStatus(project) });
  }),
);

app.get(
  "/log",
  guard((req, res) => {
    const project = requireProject(res);
    if (!project) return;
    const limit = req.query.limit ? Number(req.query.limit) : undefined;
    const entries = readLog(project.p, limit);
    res.json({ ok: true, entries });
  }),
);

app.post(
  "/log",
  guard((req, res) => {
    const project = requireProject(res);
    if (!project) return;
    const { entry } = req.body ?? {};
    if (!entry || typeof entry !== "object") {
      return res.status(400).json({ ok: false, error: "Body needs object 'entry'" });
    }
    appendLog(project.p, entry);
    res.json({ ok: true });
  }),
);

app.listen(PORT, "127.0.0.1", () => {
  console.log(`combinepro-sidecar listening on http://127.0.0.1:${PORT}`);
});
