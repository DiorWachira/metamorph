// Runs RepoLens's real offline Examiner, the code its site ships: frontend/shared.js as it stands,
// and offlineAnswer() lifted out of frontend/app.js. Only the page state is stubbed.
// Reads {question, report, focus} as JSON on stdin and writes the answer as JSON on stdout.
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const { dir, question, report, focus } = JSON.parse(fs.readFileSync(0, "utf8"));
const source = (name) => fs.readFileSync(path.join(dir, "frontend", name), "utf8");

const app = source("app.js");
const start = app.indexOf("function offlineAnswer(question)");
const end = app.indexOf("// Earlier answers are replayed");
if (start < 0 || end < 0) throw new Error("offlineAnswer not found: has app.js changed?");

// shared.js sets up the page theme as it loads; there is no page here.
const page = { documentElement: { dataset: {}, removeAttribute() {} }, querySelectorAll: () => [] };
const storage = { getItem: () => null, setItem() {} };
const context = vm.createContext({ state: { report, activeCheckId: focus ?? null }, document: page, localStorage: storage });
vm.runInContext(source("shared.js"), context);
vm.runInContext(
  "const activeCheck = () => state.report?.checks.find((check) => check.id === state.activeCheckId) || null;",
  context,
);
vm.runInContext(app.slice(start, end), context);
context.question = question;
process.stdout.write(JSON.stringify(vm.runInContext("offlineAnswer(question)", context)));
