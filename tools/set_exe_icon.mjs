#!/usr/bin/env node
/**
 * Replace every icon group in a Windows PE executable with the given .ico.
 * Used so Explorer / shortcuts show the project icon instead of MFAAvalonia's.
 */
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

async function loadResEdit() {
  const extraModules = process.env.RESEDIT_NODE_MODULES;
  if (!extraModules) {
    return import("resedit");
  }
  const pkgPath = path.join(extraModules, "resedit", "package.json");
  const pkg = JSON.parse(fs.readFileSync(pkgPath, "utf8"));
  const entry = pkg.exports?.["."] || pkg.module || pkg.main;
  if (typeof entry !== "string") {
    throw new Error(`Cannot resolve resedit entry from ${pkgPath}`);
  }
  return import(pathToFileURL(path.join(extraModules, "resedit", entry)).href);
}

const ResEdit = await loadResEdit();

if (process.argv.length < 4) {
  console.error("Usage: node set_exe_icon.mjs <exe> <ico>");
  process.exit(1);
}

const exePath = path.resolve(process.argv[2]);
const icoPath = path.resolve(process.argv[3]);
const productName = process.argv[4] || "";

if (!fs.existsSync(exePath)) {
  console.error(`EXE not found: ${exePath}`);
  process.exit(1);
}
if (!fs.existsSync(icoPath)) {
  console.error(`ICO not found: ${icoPath}`);
  process.exit(1);
}

const exeBytes = fs.readFileSync(exePath);
const iconFile = ResEdit.Data.IconFile.from(fs.readFileSync(icoPath));
const icons = iconFile.icons.map((item) => item.data);
if (icons.length === 0) {
  console.error(`No icon images found in ${icoPath}`);
  process.exit(1);
}

const exe = ResEdit.NtExecutable.from(exeBytes, { ignoreCert: true });
const res = ResEdit.NtExecutableResource.from(exe);
const groups = ResEdit.Resource.IconGroupEntry.fromEntries(res.entries);

if (groups.length === 0) {
  ResEdit.Resource.IconGroupEntry.replaceIconsForResource(
    res.entries,
    1,
    1033,
    icons,
  );
} else {
  for (const group of groups) {
    ResEdit.Resource.IconGroupEntry.replaceIconsForResource(
      res.entries,
      group.id,
      group.lang,
      icons,
    );
  }
}

if (productName) {
  const versionInfos = ResEdit.Resource.VersionInfo.fromEntries(res.entries);
  for (const vi of versionInfos) {
    const langs = vi.getAllLanguagesForStringValues();
    const targets = langs.length ? langs : [{ lang: 1033, codepage: 1200 }];
    for (const lang of targets) {
      const current = vi.getStringValues(lang);
      vi.setStringValues(lang, {
        ...current,
        ProductName: productName,
        FileDescription: productName,
        InternalName: productName,
        OriginalFilename: `${productName}.exe`,
      });
    }
    vi.outputToResourceEntries(res.entries);
  }
}

res.outputResource(exe);
fs.writeFileSync(exePath, Buffer.from(exe.generate()));
console.log(
  `Embedded ${path.basename(icoPath)} into ${exePath} (${groups.length || 1} icon group(s))`,
);
