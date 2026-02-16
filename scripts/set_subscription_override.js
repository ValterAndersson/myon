#!/usr/bin/env node

/**
 * Set Subscription Override
 *
 * CLI tool to set or remove subscription_override on a single user.
 * Used for testing, support cases, or granting premium access.
 *
 * Usage:
 *   # Grant premium override
 *   FIREBASE_SERVICE_ACCOUNT_PATH=$FIREBASE_SA_KEY \
 *   node scripts/set_subscription_override.js --user <userId> --override premium
 *
 *   # Remove override (respect App Store state)
 *   FIREBASE_SERVICE_ACCOUNT_PATH=$FIREBASE_SA_KEY \
 *   node scripts/set_subscription_override.js --user <userId> --remove
 *
 *   # View current subscription state
 *   FIREBASE_SERVICE_ACCOUNT_PATH=$FIREBASE_SA_KEY \
 *   node scripts/set_subscription_override.js --user <userId> --show
 *
 * Options:
 *   --user <userId>       Required: Firebase user ID
 *   --override <value>    Set subscription_override to this value (currently only 'premium' supported)
 *   --remove              Remove subscription_override (set to null)
 *   --show                Show current subscription state without changes
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
  userId: null,
  override: null,
  remove: false,
  show: false,
};

for (let i = 0; i < args.length; i++) {
  if (args[i] === '--user' && args[i + 1]) {
    options.userId = args[i + 1];
    i++;
  } else if (args[i] === '--override' && args[i + 1]) {
    options.override = args[i + 1];
    i++;
  } else if (args[i] === '--remove') {
    options.remove = true;
  } else if (args[i] === '--show') {
    options.show = true;
  }
}

// Validate arguments
if (!options.userId) {
  console.error('Error: --user <userId> is required');
  console.error('');
  console.error('Usage examples:');
  console.error('  node scripts/set_subscription_override.js --user abc123 --override premium');
  console.error('  node scripts/set_subscription_override.js --user abc123 --remove');
  console.error('  node scripts/set_subscription_override.js --user abc123 --show');
  process.exit(1);
}

if (!options.show && !options.remove && !options.override) {
  console.error('Error: Must specify --override <value>, --remove, or --show');
  process.exit(1);
}

if (options.override && options.remove) {
  console.error('Error: Cannot specify both --override and --remove');
  process.exit(1);
}

if (options.override && options.override !== 'premium') {
  console.error('Error: Only --override premium is currently supported');
  process.exit(1);
}

/**
 * Format timestamp for display
 */
function formatTimestamp(timestamp) {
  if (!timestamp) return 'null';
  return timestamp.toDate().toISOString();
}

/**
 * Show current subscription state
 */
async function showSubscriptionState(userId) {
  const userDoc = await db.collection('users').doc(userId).get();

  if (!userDoc.exists) {
    console.error(`Error: User ${userId} not found`);
    return false;
  }

  const userData = userDoc.data();

  console.log('\n=== Current Subscription State ===\n');
  console.log(`User ID: ${userId}`);
  console.log(`Email: ${userData.email || 'N/A'}`);
  console.log(`Name: ${userData.name || 'N/A'}`);
  console.log('');
  console.log('Subscription fields:');
  console.log(`  subscription_override: ${userData.subscription_override || 'null'}`);
  console.log(`  subscription_status: ${userData.subscription_status || 'null'}`);
  console.log(`  subscription_tier: ${userData.subscription_tier || 'null'}`);
  console.log(`  subscription_product_id: ${userData.subscription_product_id || 'null'}`);
  console.log(`  subscription_expires_at: ${formatTimestamp(userData.subscription_expires_at)}`);
  console.log(`  subscription_auto_renew_enabled: ${userData.subscription_auto_renew_enabled ?? 'null'}`);
  console.log(`  subscription_in_grace_period: ${userData.subscription_in_grace_period ?? 'null'}`);
  console.log(`  subscription_environment: ${userData.subscription_environment || 'null'}`);
  console.log(`  subscription_updated_at: ${formatTimestamp(userData.subscription_updated_at)}`);
  console.log('');

  // Compute effective access
  const hasOverride = userData.subscription_override === 'premium';
  const hasActiveSubscription = userData.subscription_status === 'active' &&
    userData.subscription_expires_at &&
    userData.subscription_expires_at.toDate() > new Date();
  const hasGracePeriod = userData.subscription_status === 'grace_period' &&
    userData.subscription_in_grace_period === true;

  const hasPremiumAccess = hasOverride || hasActiveSubscription || hasGracePeriod;

  console.log('Effective access:');
  console.log(`  Premium access: ${hasPremiumAccess ? '✅ YES' : '❌ NO'}`);

  if (hasOverride) {
    console.log(`  Reason: Override set to '${userData.subscription_override}'`);
  } else if (hasActiveSubscription) {
    console.log(`  Reason: Active subscription (expires ${formatTimestamp(userData.subscription_expires_at)})`);
  } else if (hasGracePeriod) {
    console.log('  Reason: Grace period active');
  } else {
    console.log('  Reason: Free tier');
  }

  console.log('');

  return true;
}

/**
 * Set subscription override
 */
async function setSubscriptionOverride(userId, override) {
  const userDoc = await db.collection('users').doc(userId).get();

  if (!userDoc.exists) {
    console.error(`Error: User ${userId} not found`);
    return false;
  }

  const userData = userDoc.data();

  console.log('\n=== Setting Subscription Override ===\n');
  console.log(`User ID: ${userId}`);
  console.log(`Email: ${userData.email || 'N/A'}`);
  console.log(`Current override: ${userData.subscription_override || 'null'}`);
  console.log(`New override: ${override}`);
  console.log('');

  try {
    await db.collection('users').doc(userId).update({
      subscription_override: override,
      subscription_updated_at: admin.firestore.FieldValue.serverTimestamp(),
    });

    console.log('✅ Successfully set subscription_override');
    console.log('');

    return true;

  } catch (error) {
    console.error('❌ Error setting override:', error.message);
    return false;
  }
}

/**
 * Remove subscription override
 */
async function removeSubscriptionOverride(userId) {
  const userDoc = await db.collection('users').doc(userId).get();

  if (!userDoc.exists) {
    console.error(`Error: User ${userId} not found`);
    return false;
  }

  const userData = userDoc.data();

  console.log('\n=== Removing Subscription Override ===\n');
  console.log(`User ID: ${userId}`);
  console.log(`Email: ${userData.email || 'N/A'}`);
  console.log(`Current override: ${userData.subscription_override || 'null'}`);
  console.log('');

  if (!userData.subscription_override) {
    console.log('⚠️  No override currently set, nothing to remove.');
    console.log('');
    return true;
  }

  try {
    await db.collection('users').doc(userId).update({
      subscription_override: admin.firestore.FieldValue.delete(),
      subscription_updated_at: admin.firestore.FieldValue.serverTimestamp(),
    });

    console.log('✅ Successfully removed subscription_override');
    console.log('   User will now respect App Store subscription state');
    console.log('');

    return true;

  } catch (error) {
    console.error('❌ Error removing override:', error.message);
    return false;
  }
}

// Main execution
(async () => {
  try {
    let success = false;

    if (options.show) {
      success = await showSubscriptionState(options.userId);
    } else if (options.remove) {
      success = await removeSubscriptionOverride(options.userId);
    } else if (options.override) {
      success = await setSubscriptionOverride(options.userId, options.override);
    }

    if (success) {
      // Show final state after changes
      if (!options.show) {
        await showSubscriptionState(options.userId);
      }
      process.exit(0);
    } else {
      process.exit(1);
    }

  } catch (error) {
    console.error('Script failed:', error);
    process.exit(1);
  }
})();
