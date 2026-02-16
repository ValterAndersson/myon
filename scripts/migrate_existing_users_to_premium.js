#!/usr/bin/env node

/**
 * Migrate Existing Users to Premium
 *
 * Sets subscription_override='premium' on all existing users to grandfather them in.
 * This is a one-time migration script to grant premium access to early adopters
 * before the subscription system was implemented.
 *
 * Usage:
 *   FIREBASE_SERVICE_ACCOUNT_PATH=$FIREBASE_SA_KEY \
 *   node scripts/migrate_existing_users_to_premium.js [--dry-run] [--limit <n>]
 *
 * Options:
 *   --dry-run        Don't write, just log what would be written
 *   --limit <n>      Limit number of users to process (for testing)
 *   --created-before <YYYY-MM-DD>  Only migrate users created before this date
 */

const admin = require('firebase-admin');

// Initialize Firebase Admin
const serviceAccountPath = process.env.FIREBASE_SERVICE_ACCOUNT_PATH;

try {
  if (serviceAccountPath) {
    const serviceAccount = require(serviceAccountPath);
    admin.initializeApp({
      credential: admin.credential.cert(serviceAccount),
    });
    console.log('Initialized with service account:', serviceAccountPath);
  } else {
    // Use default credentials (gcloud auth)
    admin.initializeApp({
      projectId: 'myon-53d85',
    });
    console.log('Initialized with default credentials (gcloud auth)');
  }
} catch (e) {
  if (!e.message.includes('already exists')) {
    throw e;
  }
}

const db = admin.firestore();

// Parse command line arguments
const args = process.argv.slice(2);
const options = {
  dryRun: false,
  limit: null,
  createdBefore: null,
};

for (let i = 0; i < args.length; i++) {
  if (args[i] === '--dry-run') {
    options.dryRun = true;
  } else if (args[i] === '--limit' && args[i + 1]) {
    options.limit = parseInt(args[i + 1], 10);
    i++;
  } else if (args[i] === '--created-before' && args[i + 1]) {
    options.createdBefore = args[i + 1];
    i++;
  }
}

/**
 * Process a single user
 */
async function processUser(userDoc, options) {
  const userId = userDoc.id;
  const userData = userDoc.data();

  // Skip users who already have subscription_override set
  if (userData.subscription_override) {
    console.log(`  ⏭️  User ${userId}: Already has override="${userData.subscription_override}", skipping`);
    return { skipped: true, reason: 'already_has_override' };
  }

  // Check created_at filter
  if (options.createdBefore && userData.created_at) {
    const createdAt = userData.created_at.toDate();
    const cutoffDate = new Date(options.createdBefore);

    if (createdAt >= cutoffDate) {
      console.log(`  ⏭️  User ${userId}: Created ${createdAt.toISOString()}, after cutoff ${options.createdBefore}, skipping`);
      return { skipped: true, reason: 'after_cutoff' };
    }
  }

  if (options.dryRun) {
    console.log(`  [DRY RUN] Would set subscription_override='premium' for user ${userId}`);
    return { updated: true, dryRun: true };
  }

  try {
    await db.collection('users').doc(userId).update({
      subscription_override: 'premium',
      subscription_updated_at: admin.firestore.FieldValue.serverTimestamp(),
    });

    console.log(`  ✅ User ${userId}: Set subscription_override='premium'`);
    return { updated: true };

  } catch (error) {
    console.error(`  ❌ User ${userId}: Error:`, error.message);
    return { error: error.message };
  }
}

/**
 * Main migration function
 */
async function migrateUsers(options) {
  console.log('\n=== Migrate Existing Users to Premium ===\n');
  console.log('Options:', options);
  console.log('');

  const stats = {
    total: 0,
    updated: 0,
    skipped: 0,
    errors: 0,
  };

  // Fetch all users
  let query = db.collection('users');

  if (options.limit) {
    query = query.limit(options.limit);
  }

  const snapshot = await query.get();

  if (snapshot.empty) {
    console.log('No users found.');
    return stats;
  }

  console.log(`Found ${snapshot.size} users to process.\n`);

  // Process users sequentially to avoid rate limits
  for (const userDoc of snapshot.docs) {
    stats.total++;

    const result = await processUser(userDoc, options);

    if (result.updated) {
      stats.updated++;
    } else if (result.skipped) {
      stats.skipped++;
    } else if (result.error) {
      stats.errors++;
    }
  }

  return stats;
}

// Run the migration
migrateUsers(options)
  .then((stats) => {
    console.log('\n=== Migration Complete ===\n');
    console.log(`Total users processed: ${stats.total}`);
    console.log(`Updated: ${stats.updated}`);
    console.log(`Skipped: ${stats.skipped}`);
    console.log(`Errors: ${stats.errors}`);
    console.log('');

    if (options.dryRun) {
      console.log('[DRY RUN] No changes were written.');
    }

    process.exit(0);
  })
  .catch((error) => {
    console.error('Migration failed:', error);
    process.exit(1);
  });
