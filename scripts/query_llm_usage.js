/**
 * Query LLM usage from the llm_usage Firestore collection.
 *
 * Aggregates token counts and estimated costs by week, category, system,
 * and optionally by user. Uses pricing from a local config (update when
 * Google publishes new rates).
 *
 * Usage:
 *   node scripts/query_llm_usage.js                         # current week
 *   node scripts/query_llm_usage.js --weeks 4               # last 4 weeks
 *   node scripts/query_llm_usage.js --user <uid>            # single user
 *   node scripts/query_llm_usage.js --weeks 4 --csv         # CSV output
 */

const admin = require('firebase-admin');
const path = require('path');

// --- Firebase init ---
const saKey = process.env.GOOGLE_APPLICATION_CREDENTIALS
  || path.join(process.env.HOME, '.config/povver/myon-53d85-firebase-adminsdk-fbsvc-ca7beb1435.json');

if (!admin.apps.length) {
  admin.initializeApp({ credential: admin.credential.cert(require(saKey)) });
}
const db = admin.firestore();

// --- Pricing (EUR per 1M tokens) — update when Google publishes new rates ---
const PRICING = {
  'gemini-2.5-flash':  { input: 0.15, output: 0.60, thinking: 0.15 },
  'gemini-2.5-pro':    { input: 1.25, output: 5.00, thinking: 1.25 },
  'gemini-2.0-flash':  { input: 0.10, output: 0.40, thinking: 0.00 },
  'gemini-1.5-flash':  { input: 0.075, output: 0.30, thinking: 0.00 },
  'gemini-1.5-pro':    { input: 1.25, output: 5.00, thinking: 0.00 },
};

function estimateCostEur(model, promptTokens, completionTokens, thinkingTokens) {
  const rates = PRICING[model] || { input: 0, output: 0, thinking: 0 };
  return (
    (promptTokens / 1_000_000) * rates.input +
    (completionTokens / 1_000_000) * rates.output +
    ((thinkingTokens || 0) / 1_000_000) * rates.thinking
  );
}

// --- ISO week helper (Monday-based) ---
function getISOWeek(date) {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  d.setUTCDate(d.getUTCDate() + 4 - (d.getUTCDay() || 7));
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  const weekNo = Math.ceil(((d - yearStart) / 86400000 + 1) / 7);
  return `${d.getUTCFullYear()}-W${String(weekNo).padStart(2, '0')}`;
}

// --- CLI args ---
const args = process.argv.slice(2);
function getArg(name, defaultValue) {
  const idx = args.indexOf(`--${name}`);
  if (idx === -1) return defaultValue;
  return args[idx + 1] || defaultValue;
}
const hasFlag = (name) => args.includes(`--${name}`);

const weeks = parseInt(getArg('weeks', '1'), 10);
const filterUser = getArg('user', null);
const csvMode = hasFlag('csv');

async function main() {
  // Time window: last N weeks (Monday-based)
  const now = new Date();
  const startDate = new Date(now);
  startDate.setDate(startDate.getDate() - (weeks * 7));
  startDate.setHours(0, 0, 0, 0);

  console.error(`Querying llm_usage from ${startDate.toISOString()} to now (${weeks} week(s))`);
  if (filterUser) console.error(`Filtering by user: ${filterUser}`);

  // Build query (equality filters must precede inequality for composite index)
  let query = db.collection('llm_usage');

  if (filterUser) {
    query = query.where('user_id', '==', filterUser);
  }

  query = query
    .where('created_at', '>=', startDate)
    .orderBy('created_at', 'asc');

  const snapshot = await query.get();
  console.error(`Found ${snapshot.size} usage records\n`);

  if (snapshot.empty) {
    console.log('No usage data found for the specified period.');
    process.exit(0);
  }

  // Aggregate by week + category + system + user
  const buckets = {};    // week → aggregated totals
  const byCategory = {}; // category → totals
  const bySystem = {};   // system → totals
  const byUser = {};     // user_id → totals
  let grandTotal = { prompt: 0, completion: 0, thinking: 0, total: 0, cost: 0, calls: 0 };

  snapshot.forEach(doc => {
    const d = doc.data();
    const createdAt = d.created_at?.toDate?.() || new Date();
    const week = getISOWeek(createdAt);
    const model = d.model || 'unknown';
    const prompt = d.prompt_tokens || 0;
    const completion = d.completion_tokens || 0;
    const thinking = d.thinking_tokens || 0;
    const total = d.total_tokens || 0;
    const cost = estimateCostEur(model, prompt, completion, thinking);

    const add = (bucket) => {
      bucket.prompt = (bucket.prompt || 0) + prompt;
      bucket.completion = (bucket.completion || 0) + completion;
      bucket.thinking = (bucket.thinking || 0) + thinking;
      bucket.total = (bucket.total || 0) + total;
      bucket.cost = (bucket.cost || 0) + cost;
      bucket.calls = (bucket.calls || 0) + 1;
    };

    // By week
    if (!buckets[week]) buckets[week] = {};
    const weekKey = `${d.category}|${d.system}`;
    if (!buckets[week][weekKey]) buckets[week][weekKey] = { category: d.category, system: d.system };
    add(buckets[week][weekKey]);

    // By category
    if (!byCategory[d.category]) byCategory[d.category] = {};
    add(byCategory[d.category]);

    // By system
    if (!bySystem[d.system]) bySystem[d.system] = {};
    add(bySystem[d.system]);

    // By user
    const uid = d.user_id || '(system)';
    if (!byUser[uid]) byUser[uid] = {};
    add(byUser[uid]);

    // Grand total
    add(grandTotal);
  });

  if (csvMode) {
    console.log('week,category,system,calls,prompt_tokens,completion_tokens,thinking_tokens,total_tokens,estimated_cost_eur');
    for (const [week, entries] of Object.entries(buckets).sort()) {
      for (const [, data] of Object.entries(entries).sort()) {
        console.log([
          week, data.category, data.system, data.calls,
          data.prompt, data.completion, data.thinking, data.total,
          data.cost.toFixed(6),
        ].join(','));
      }
    }
    return;
  }

  // --- Pretty print ---
  const fmt = (n) => n.toLocaleString('en-US');
  const eur = (n) => `€${n.toFixed(4)}`;

  // Weekly breakdown
  console.log('=== WEEKLY BREAKDOWN ===\n');
  for (const [week, entries] of Object.entries(buckets).sort()) {
    console.log(`  ${week}:`);
    for (const [, data] of Object.entries(entries).sort()) {
      console.log(`    ${data.category} / ${data.system}: ${fmt(data.calls)} calls, ${fmt(data.total)} tokens, ${eur(data.cost)}`);
    }
  }

  // By category
  console.log('\n=== BY CATEGORY ===\n');
  for (const [cat, data] of Object.entries(byCategory).sort()) {
    console.log(`  ${cat}: ${fmt(data.calls)} calls, ${fmt(data.total)} tokens, ${eur(data.cost)}`);
  }

  // By system
  console.log('\n=== BY SYSTEM ===\n');
  for (const [sys, data] of Object.entries(bySystem).sort()) {
    console.log(`  ${sys}: ${fmt(data.calls)} calls, ${fmt(data.total)} tokens, ${eur(data.cost)}`);
  }

  // By user (top 10)
  console.log('\n=== BY USER (top 10) ===\n');
  const sortedUsers = Object.entries(byUser).sort((a, b) => b[1].cost - a[1].cost).slice(0, 10);
  for (const [uid, data] of sortedUsers) {
    console.log(`  ${uid}: ${fmt(data.calls)} calls, ${fmt(data.total)} tokens, ${eur(data.cost)}`);
  }

  // Grand total
  console.log('\n=== GRAND TOTAL ===\n');
  console.log(`  Calls: ${fmt(grandTotal.calls)}`);
  console.log(`  Tokens: ${fmt(grandTotal.total)} (prompt: ${fmt(grandTotal.prompt)}, completion: ${fmt(grandTotal.completion)}, thinking: ${fmt(grandTotal.thinking)})`);
  console.log(`  Estimated cost: ${eur(grandTotal.cost)}`);

  // Margin check
  const uniqueUsers = Object.keys(byUser).filter(u => u !== '(system)').length;
  if (uniqueUsers > 0) {
    const userCost = Object.entries(byUser)
      .filter(([uid]) => uid !== '(system)')
      .reduce((sum, [, d]) => sum + d.cost, 0);
    console.log(`\n  Per-user average (${uniqueUsers} users): ${eur(userCost / uniqueUsers)} / ${weeks} week(s)`);
  }
}

main().catch(err => {
  console.error('Error:', err.message);
  process.exit(1);
});
