function toSlug(name) {
  if (!name) return '';
  let s = String(name).toLowerCase();
  // remove content inside parentheses for canonicalization
  s = s.replace(/\([^\)]*\)/g, '');
  // replace non-alphanumeric with hyphens
  s = s.replace(/[^a-z0-9]+/g, '-');
  // collapse multiple hyphens
  s = s.replace(/-+/g, '-');
  // trim hyphens
  s = s.replace(/^-|-$/g, '');
  return s;
}

function uniqueArray(arr) {
  return Array.from(new Set((arr || []).filter(Boolean)));
}

function buildAliasSlugs(name, aliases) {
  const names = uniqueArray([name, ...(aliases || [])]);
  const slugs = names.map(n => toSlug(n)).filter(Boolean);
  return uniqueArray(slugs);
}

module.exports = { toSlug, buildAliasSlugs, uniqueArray };


