const admin = require('firebase-admin');
const path = require('path');

const saKey = process.env.GOOGLE_APPLICATION_CREDENTIALS
  || path.join(process.env.HOME, '.config/povver/myon-53d85-firebase-adminsdk-fbsvc-ca7beb1435.json');

if (!admin.apps.length) {
  admin.initializeApp({ credential: admin.credential.cert(require(saKey)) });
}
const db = admin.firestore();

const USER_ID = 'xLRyVOI0XKSFsTXSFbGSvui8FJf2';

function ts(v) {
  if (v && v.toDate) return v.toDate().toISOString();
  return v;
}

function clean(obj) {
  if (!obj || typeof obj !== 'object') return obj;
  const out = {};
  for (const [k, v] of Object.entries(obj)) {
    if (v && v.toDate) out[k] = v.toDate().toISOString();
    else if (Array.isArray(v)) out[k] = v.map(clean);
    else if (v && typeof v === 'object') out[k] = clean(v);
    else out[k] = v;
  }
  return out;
}

async function main() {
  // Insights (latest 3)
  const insightsSnap = await db.collection('users').doc(USER_ID)
    .collection('analysis_insights')
    .orderBy('created_at', 'desc')
    .limit(3)
    .get();

  console.log('=== ANALYSIS INSIGHTS ===');
  for (const doc of insightsSnap.docs) {
    console.log(JSON.stringify({ id: doc.id, ...clean(doc.data()) }, null, 2));
    console.log('---');
  }

  // Daily briefs (latest 3)
  const briefsSnap = await db.collection('users').doc(USER_ID)
    .collection('daily_briefs')
    .orderBy('created_at', 'desc')
    .limit(3)
    .get();

  console.log('\n=== DAILY BRIEFS ===');
  for (const doc of briefsSnap.docs) {
    console.log(JSON.stringify({ id: doc.id, ...clean(doc.data()) }, null, 2));
    console.log('---');
  }

  // Weekly reviews (latest 2)
  const reviewsSnap = await db.collection('users').doc(USER_ID)
    .collection('weekly_reviews')
    .orderBy('created_at', 'desc')
    .limit(2)
    .get();

  console.log('\n=== WEEKLY REVIEWS ===');
  for (const doc of reviewsSnap.docs) {
    console.log(JSON.stringify({ id: doc.id, ...clean(doc.data()) }, null, 2));
    console.log('---');
  }
}

main().then(() => process.exit(0)).catch(e => { console.error(e); process.exit(1); });
