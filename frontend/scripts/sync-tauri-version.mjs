import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

function extractCargoPackageVersion(cargoTomlText) {
  const lines = cargoTomlText.split(/\r?\n/);
  let inPackageSection = false;
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith("[") && trimmed.endsWith("]")) {
      inPackageSection = trimmed === "[package]";
      continue;
    }
    if (!inPackageSection) continue;
    const m = trimmed.match(/^version\s*=\s*"([^"]+)"\s*$/);
    if (m) return m[1];
  }
  return "";
}

async function readJson(filePath) {
  const raw = await fs.readFile(filePath, "utf8");
  return JSON.parse(raw);
}

async function writeJson(filePath, value) {
  const content = `${JSON.stringify(value, null, 2)}\n`;
  await fs.writeFile(filePath, content, "utf8");
}

async function syncTauriConfigVersion(rootDir, version) {
  const configPaths = [
    path.join(rootDir, "src-tauri", "tauri.conf.json"),
    path.join(rootDir, "src-tauri", "tauri.gpu.nsis.conf.json"),
  ];

  for (const configPath of configPaths) {
    const json = await readJson(configPath);
    if (json?.version !== version) {
      json.version = version;
      await writeJson(configPath, json);
      process.stdout.write(`[sync-version] ${path.relative(rootDir, configPath)} -> ${version}\n`);
    }
  }
}

async function main() {
  const rootDir = path.resolve(__dirname, "..", "..");
  const cargoTomlPath = path.join(rootDir, "src-tauri", "Cargo.toml");
  const cargoTomlText = await fs.readFile(cargoTomlPath, "utf8");
  const version = extractCargoPackageVersion(cargoTomlText);

  if (!version) {
    process.stderr.write("[sync-version] 未能从 src-tauri/Cargo.toml 的 [package] 读取 version\n");
    process.exitCode = 1;
    return;
  }

  await syncTauriConfigVersion(rootDir, version);
}

await main();
