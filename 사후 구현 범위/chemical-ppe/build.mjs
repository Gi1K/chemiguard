// The prework archive is immutable. Only this build's allowlisted output ships.
import { readFile, writeFile, mkdir, rm, copyFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { createHash } from "node:crypto";

const root = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(root, "../..");
const prework = path.join(repo, "사전 구현 범위/04_화학보호복_기존페이지");
const baseline = path.join(prework, "demo/video-gallery/kit-catalog");
const out = path.join(root, "dist/kit-catalog");
const snapshot = JSON.parse(
  await readFile(
    path.join(
      repo,
      "사전 구현 범위/03_화학보호복_페이지_PRD/baseline_snapshot.json",
    ),
    "utf8",
  ),
);
for (const item of snapshot.files) {
  const hash = createHash("sha256")
    .update(await readFile(path.join(prework, item.path)))
    .digest("hex");
  if (hash !== item.sha256)
    throw new Error(`사전 기준선 변경 감지: ${item.path}`);
}
const apiBase = (process.env.PUBLIC_API_BASE || "").replace(/\/$/, "");
if (apiBase) {
  const url = new URL(apiBase);
  if (
    url.protocol !== "https:" ||
    url.username ||
    url.password ||
    url.pathname !== "/" ||
    url.search ||
    url.hash
  )
    throw new Error(
      "PUBLIC_API_BASE must be an HTTPS origin without credentials, path or query.",
    );
}
await rm(path.join(root, "dist"), { recursive: true, force: true });
await mkdir(out, { recursive: true });
for (const name of [
  "core",
  "drafts",
  "catalog",
  "photo-upload",
  "counselor",
  "catalog-sync",
  "bootstrap",
]) {
  await copyFile(
    path.join(root, `web/${name}.js`),
    path.join(out, `${name}.js`),
  );
}
await writeFile(
  path.join(out, "style.css"),
  (await readFile(path.join(baseline, "style.css"), "utf8")) +
    "\n" +
    (await readFile(path.join(root, "web/public.css"), "utf8")) +
    "\n" +
    (await readFile(path.join(root, "web/catalog.css"), "utf8")),
);
let html = await readFile(path.join(root, "web/index.html"), "utf8");
html = html.replace(
  "<!-- API_CONFIG -->",
  '<script src="config.js" defer></script>',
);
await writeFile(path.join(out, "index.html"), html);
await writeFile(
  path.join(out, "config.js"),
  `window.PPE_CONFIG = ${JSON.stringify({ apiBase })};\n`,
);
// Keep identity/rights evidence, remove local paths and unapproved image URLs.
const catalog = JSON.parse(
  await readFile(path.join(baseline, "catalog-data.json"), "utf8"),
);
const privateKeys = new Set([
  "path",
  "preview_path",
  "local_path",
  "local_file",
  "media_url",
  "cell_html",
]);
function publicData(value) {
  if (Array.isArray(value)) return value.map(publicData);
  if (value && typeof value === "object")
    return Object.fromEntries(
      Object.entries(value)
        .filter(([k]) => !privateKeys.has(k))
        .map(([k, v]) => [k, publicData(v)]),
    );
  if (typeof value === "string" && /^(file:|\/home\/|\/tmp\/)/.test(value))
    return "[로컬 자료 경로 비공개]";
  return value;
}
await writeFile(
  path.join(out, "catalog-data.json"),
  JSON.stringify(publicData(catalog)),
);
await copyFile(
  path.join(root, "web/criteria.html"),
  path.join(out, "criteria.html"),
);
await writeFile(
  path.join(root, "dist/index.html"),
  '<!doctype html><html lang="ko"><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=/kit-catalog/"><title>ChemiGuard</title><a href="/kit-catalog/">ChemiGuard 열기</a></html>',
);
await writeFile(
  path.join(root, "dist/build-manifest.json"),
  JSON.stringify(
    {
      prework: "2026-10-08",
      implementation: "2026-10-09",
      products: catalog.products.length,
      product_sources: catalog.product_sources.length,
      redistributed_product_photos: 0,
      baseline_sha256_verified: snapshot.files.length,
      api_base: apiBase || "same-origin",
      local_photos_in_build: false,
    },
    null,
    2,
  ),
);
console.log(
  `Built dist: ${catalog.products.length} products; ${snapshot.files.length} prework hashes verified; 0 restricted photos.`,
);
