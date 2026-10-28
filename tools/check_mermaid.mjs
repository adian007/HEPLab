// Validate every checked-in Mermaid block with the official Mermaid parser.
// Setup: npm install --prefix .cache/handbook-tools --ignore-scripts mermaid@12.2.0 jsdom@26.1.0
// Run: node tools/check_mermaid.mjs [.cache/handbook-tools]
import { readFile, readdir } from "node:fs/promises";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const dependencyRoot = resolve(root, process.argv[2] ?? ".cache/handbook-tools");
const require = createRequire(pathToFileURL(join(dependencyRoot, "package.json")));
const { JSDOM } = await import(pathToFileURL(require.resolve("jsdom")).href);
const dom = new JSDOM("<!doctype html><html><body></body></html>");
globalThis.window = dom.window;
globalThis.document = dom.window.document;
const mermaid = (await import(pathToFileURL(require.resolve("mermaid")).href)).default;
mermaid.initialize({ startOnLoad: false, securityLevel: "strict" });

async function markdownFiles(directory) {
  const output = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    if (entry.name.startsWith(".") || entry.name === "node_modules" || entry.name === "target") continue;
    const path = join(directory, entry.name);
    if (entry.isDirectory()) output.push(...await markdownFiles(path));
    else if (entry.name.endsWith(".md")) output.push(path);
  }
  return output;
}

let blocks = 0;
let failures = 0;
const files = [join(root, "README.md")];
for (const folder of ["docs", "contracts", "notebooks", "tests/golden", "src", "tools", "kernels", "deploy"]) {
  files.push(...await markdownFiles(join(root, folder)));
}
for (const path of files.sort()) {
  const content = await readFile(path, "utf8");
  for (const match of content.matchAll(/```mermaid\s*\n([\s\S]*?)```/g)) {
    blocks += 1;
    try {
      await mermaid.parse(match[1]);
    } catch (error) {
      failures += 1;
      console.error(`${path}: Mermaid parse failed: ${error.message}`);
    }
  }
}
dom.window.close();
console.log(`Mermaid syntax: ${blocks} blocks parsed across ${files.length} Markdown files; ${failures} failures.`);
process.exitCode = failures ? 1 : 0;
