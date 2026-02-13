import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function runSync() {
  const syncScriptPath = path.join(__dirname, "sync-tauri-version.mjs");
  const p = spawn(process.execPath, [syncScriptPath], { stdio: "inherit" });
  await new Promise((resolve, reject) => {
    p.on("error", reject);
    p.on("exit", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`sync-tauri-version 退出码 ${code ?? "unknown"}`));
    });
  });
}

async function runTauri(args) {
  const p = spawn("tauri", args, { stdio: "inherit" });
  await new Promise((resolve) => {
    p.on("exit", (code) => {
      process.exitCode = code ?? 1;
      resolve();
    });
  });
}

await runSync();
await runTauri(process.argv.slice(2));
