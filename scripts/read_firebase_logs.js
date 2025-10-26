#!/usr/bin/env node

/**
 * Script to read Firebase Functions logs programmatically
 * Usage: node read_firebase_logs.js [functionName] [minutes]
 * Example: node read_firebase_logs.js proposeCards 5
 */

const { exec } = require('child_process');
const util = require('util');
const execPromise = util.promisify(exec);

async function readFirebaseLogs(functionName = null, minutesAgo = 10) {
  try {
    // Calculate time range
    const endTime = new Date();
    const startTime = new Date(endTime.getTime() - minutesAgo * 60 * 1000);
    
    // Format times for firebase functions:log command
    const startTimeStr = startTime.toISOString();
    const endTimeStr = endTime.toISOString();
    
    console.log(`\n📋 Reading Firebase Functions logs from ${minutesAgo} minutes ago...`);
    console.log(`Time range: ${startTimeStr} to ${endTimeStr}\n`);
    
    // Build command
    let command = `firebase functions:log -n 500`;
    if (functionName) {
      command = `firebase functions:log -n 500 | grep -i ${functionName}`;
    }
    
    console.log(`Executing: ${command}\n`);
    console.log('=' .repeat(80));
    
    // Execute command
    const { stdout, stderr } = await execPromise(command);
    
    if (stderr && !stderr.includes('Warning')) {
      console.error('Stderr:', stderr);
    }
    
    // Parse and format logs
    const lines = stdout.split('\n').filter(line => line.trim());
    
    // Filter by time if needed
    const recentLines = lines.filter(line => {
      // Firebase logs format: "2024-12-26 10:30:45.123 I functionName: message"
      const timeMatch = line.match(/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})/);
      if (!timeMatch) return true; // Include lines without timestamps
      
      const logTime = new Date(timeMatch[1].replace(' ', 'T') + 'Z');
      return logTime >= startTime && logTime <= endTime;
    });
    
    // Group logs by function and highlight important patterns
    const importantPatterns = [
      /\[proposeCards\]/i,
      /\[auth\]/i,
      /\[streamAgentNormalized\]/i,
      /\[invokeCanvasOrchestrator\]/i,
      /error/i,
      /failed/i,
      /401/i,
      /403/i,
      /invalid/i,
      /missing/i,
      /correlation/i,
      /created_card_ids/i,
      /agent_propose/i,
      /agent_publish_failed/i,
      /hasApiKey/i,
      /hasUserHeader/i,
      /X-User-Id/i,
      /X-API-Key/i
    ];
    
    console.log('\n🔍 Relevant Logs:\n');
    
    let currentFunction = '';
    recentLines.forEach(line => {
      // Extract function name
      const funcMatch = line.match(/\s([a-zA-Z]+):\s/);
      if (funcMatch && funcMatch[1] !== currentFunction) {
        currentFunction = funcMatch[1];
        console.log(`\n📦 Function: ${currentFunction}`);
        console.log('-'.repeat(40));
      }
      
      // Highlight important lines
      const isImportant = importantPatterns.some(pattern => pattern.test(line));
      if (isImportant) {
        // Color code based on severity
        if (/error|failed|401|403|invalid/i.test(line)) {
          console.log(`❌ ${line}`);
        } else if (/warning|missing/i.test(line)) {
          console.log(`⚠️  ${line}`);
        } else if (/created_card_ids|agent_propose|ok/i.test(line)) {
          console.log(`✅ ${line}`);
        } else {
          console.log(`ℹ️  ${line}`);
        }
      } else if (!functionName) {
        // Show all lines if no specific function is requested
        console.log(`   ${line}`);
      }
    });
    
    console.log('\n' + '='.repeat(80));
    console.log(`\n📊 Summary: Found ${recentLines.length} log entries in the last ${minutesAgo} minutes`);
    
    // Look for specific error patterns
    const errors = recentLines.filter(line => /error|failed|401|403|invalid/i.test(line));
    if (errors.length > 0) {
      console.log(`\n⚠️  Found ${errors.length} potential errors:`);
      errors.forEach(err => console.log(`   - ${err.substring(0, 150)}...`));
    }
    
    // Check for proposeCards specific issues
    const proposeCardsLogs = recentLines.filter(line => /\[proposeCards\]/i.test(line));
    if (proposeCardsLogs.length > 0) {
      console.log(`\n📝 proposeCards activity (${proposeCardsLogs.length} entries):`);
      proposeCardsLogs.forEach(log => {
        if (/hasApiKey.*false/i.test(log)) {
          console.log('   ❌ Missing API key!');
        }
        if (/hasUserHeader.*false/i.test(log)) {
          console.log('   ❌ Missing User ID header!');
        }
        if (/created_card_ids/i.test(log)) {
          const match = log.match(/created_card_ids.*\[([^\]]*)\]/);
          if (match) {
            console.log(`   ✅ Created cards: [${match[1]}]`);
          }
        }
      });
    }
    
  } catch (error) {
    console.error('Error reading Firebase logs:', error.message);
    console.log('\nMake sure you have Firebase CLI installed and are logged in:');
    console.log('  npm install -g firebase-tools');
    console.log('  firebase login');
    console.log('  firebase use myon-53d85');
  }
}

// Parse command line arguments
const args = process.argv.slice(2);
const functionName = args[0] || null;
const minutes = parseInt(args[1]) || 10;

// Run the script
readFirebaseLogs(functionName, minutes);
