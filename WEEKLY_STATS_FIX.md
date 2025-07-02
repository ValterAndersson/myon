# Weekly Stats Recalculation Fix

## Issue Summary
The automated weekly stats recalculation was not working, despite manual recalculation functioning correctly. Stats had not been recalculated automatically since the last week.

## Root Cause Analysis

### Primary Issue: Firebase Functions v2 Export Problem
The main issue was in how the scheduled function was being exported in `firebase_functions/functions/index.js`. 

**Problem**: The `weeklyStatsRecalculation` function was defined using Firebase Functions v2 syntax (`onSchedule` from `firebase-functions/v2/scheduler`) but was being handled incorrectly in the export structure.

**Technical Details**:
- The function was correctly defined with v2 syntax in `triggers/weekly-analytics.js`
- However, the import/export structure in `index.js` was not optimized for v2 functions
- This could cause deployment issues where the scheduled function doesn't get properly registered with Cloud Scheduler

### Secondary Issues Addressed
1. **Missing Region Configuration**: Added explicit `region: 'us-central1'` to ensure proper deployment
2. **Insufficient Logging**: Added comprehensive logging for better debugging and monitoring
3. **Error Tracking**: Enhanced error reporting with timestamps

## Fixes Implemented

### 1. Corrected Function Export Structure (`index.js`)
- Cleaned up the import structure for the v2 scheduled function
- Ensured proper export of the v2 scheduled function
- Added clear comments distinguishing v2 function exports

### 2. Enhanced Scheduled Function Configuration (`weekly-analytics.js`)
```javascript
exports.weeklyStatsRecalculation = onSchedule({
  schedule: '0 2 * * *', // Daily at 2 AM UTC
  timeZone: 'UTC',
  region: 'us-central1', // Explicitly set region for v2 functions
  retryConfig: {
    retryCount: 3,
    maxRetryDuration: '600s'
  }
}, async (event) => {
  // Enhanced function logic with better logging
});
```

### 3. Improved Logging and Monitoring
- Added start and completion logs with timestamps
- Enhanced error reporting for better debugging
- Added detailed result tracking (successful/failed operations, active users count)

## Function Behavior
The scheduled function:
- Runs daily at 2:00 AM UTC
- Processes users who have completed workouts in the last 2 weeks
- Recalculates stats for both current week and previous week for each active user
- Processes users in batches of 10 to avoid overwhelming the system
- Has retry logic (3 attempts with exponential backoff)

## Next Steps
1. **Deploy the Fixed Functions**: Run `firebase deploy --only functions` to deploy the corrected code
2. **Monitor Logs**: Check Firebase Function logs tomorrow morning (after 2 AM UTC) to verify the function runs successfully
3. **Verify Results**: Confirm that weekly stats are being updated automatically by checking a few user accounts

## Verification Commands
After deployment, you can verify the fix by:
```bash
# Check if the scheduled function is properly deployed
firebase functions:list | grep weeklyStatsRecalculation

# Monitor function logs
firebase functions:log --only weeklyStatsRecalculation

# Test manual recalculation (should still work)
# Call manualWeeklyStatsRecalculation from your app
```

## Manual Fallback
If issues persist, the `manualWeeklyStatsRecalculation` function remains available as a callable function from your app and continues to work correctly.