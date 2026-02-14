const admin = require('firebase-admin');
const path = require('path');

const saKey = process.env.GOOGLE_APPLICATION_CREDENTIALS
  || path.join(process.env.HOME, '.config/povver/myon-53d85-firebase-adminsdk-fbsvc-ca7beb1435.json');

admin.initializeApp({ credential: admin.credential.cert(require(saKey)) });
const db = admin.firestore();

async function main() {
  const users = await db.collection('users').limit(30).get();
  console.log(`Checking ${users.size} users for analysis data...`);

  for (const u of users.docs) {
    const insights = await db.collection('users').doc(u.id).collection('analysis_insights').limit(1).get();
    const briefs = await db.collection('users').doc(u.id).collection('daily_briefs').limit(1).get();
    const reviews = await db.collection('users').doc(u.id).collection('weekly_reviews').limit(1).get();

    const has = [];
    if (insights.size > 0) has.push('insights');
    if (briefs.size > 0) has.push('briefs');
    if (reviews.size > 0) has.push('reviews');

    if (has.length > 0) {
      console.log(`  ${u.id}: ${has.join(', ')}`);
    }
  }
}

main().then(() => process.exit(0)).catch(e => { console.error(e); process.exit(1); });
