/* The phone link: the teacher's page seals, the parent's phone opens. Node only, no packages.
     node tests/test_homelink.cjs
   Checks that ui/portal.html and site_src/home/index.html carry the same sealing code, that a
   page sealed by one opens in the other with the right code only, and that a changed link fails. */
const fs = require("fs"); const path = require("path"); const assert = require("assert");
const root = path.join(__dirname, "..");
const block = file => { const s = fs.readFileSync(path.join(root, file), "utf8"); const a = s.indexOf("/* SEAL-START"), b = s.indexOf("/* SEAL-END */");
  assert.ok(a >= 0 && b > a, `${file} has no SEAL block`); return s.slice(a, b); };
const portal = block("ui/portal.html"), home = block("site_src/home/index.html");
assert.strictEqual(portal, home, "the portal and the phone page must use the same sealing code");
const load = src => new Function(`${src}; return { sealPage, openPage, cleanCode };`)();
const teacher = load(portal), phone = load(home);
(async () => {
  const page = { v: 1, child: "Kamau", latest: [{ area: "Mathematics", level: "ME", id: "R-01234" }], note: "Habari 🌍 ".repeat(200) };
  const sealed = await teacher.sealPage(page, "K7PM3QXD", 1000);
  assert.match(sealed, /^1\.[\w-]+\.[\w-]+\.[\w-]+$/, "format.salt.iv.sealed, safe in a link");
  assert.ok(!sealed.includes("Kamau") && !sealed.includes("R-01234"), "nothing readable in the link");
  assert.ok(sealed.length < JSON.stringify(page).length, "deflated before sealing");
  assert.deepStrictEqual(await phone.openPage(sealed, "k7pm-3qxd", 1000), page, "small letters and the dash are fine");
  await assert.rejects(phone.openPage(sealed, "K7PM3QXE", 1000), /wrong-code/);
  const parts = sealed.split("."); const ct = parts[3]; parts[3] = (ct[5] === "A" ? "B" : "A") + ct.slice(1, 5) + ct.slice(6);
  await assert.rejects(phone.openPage(parts.join("."), "K7PM3QXD", 1000), /wrong-code|bad-link/, "a changed link does not open");
  await assert.rejects(phone.openPage("nonsense", "K7PM3QXD", 1000), /bad-link/);
  const a = await teacher.sealPage(page, "K7PM3QXD", 1000), b = await teacher.sealPage(page, "K7PM3QXD", 1000);
  assert.notStrictEqual(a, b, "a fresh salt and IV every time");
  console.log("phone link: 8 checks passed");
})().catch(e => { console.error(e); process.exit(1); });
