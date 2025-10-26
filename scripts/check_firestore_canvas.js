#!/usr/bin/env node

/**
 * Check Firestore canvas data directly
 */

const admin = require('firebase-admin');

// Initialize admin SDK
if (!admin.apps.length) {
  admin.initializeApp({
    projectId: 'myon-53d85',
  });
}

const db = admin.firestore();

async function checkCanvas(userId, canvasId) {
  console.log('\n🔍 Checking Firestore Canvas Data');
  console.log('=' .repeat(60));
  console.log(`User ID: ${userId}`);
  console.log(`Canvas ID: ${canvasId}`);
  console.log();

  try {
    // Check canvas document
    const canvasRef = db.collection('users').doc(userId).collection('canvases').doc(canvasId);
    const canvasDoc = await canvasRef.get();
    
    if (!canvasDoc.exists) {
      console.log('❌ Canvas document not found!');
      return;
    }
    
    console.log('✅ Canvas exists');
    const canvasData = canvasDoc.data();
    console.log(`   Created: ${canvasData.created_at?.toDate?.() || canvasData.created_at}`);
    console.log(`   Purpose: ${canvasData.purpose || 'unknown'}`);
    console.log();
    
    // Check cards
    const cardsSnapshot = await canvasRef.collection('cards').get();
    console.log(`📇 Cards: ${cardsSnapshot.size} total`);
    
    const cardTypes = {};
    cardsSnapshot.forEach(doc => {
      const card = doc.data();
      const type = card.type || 'unknown';
      cardTypes[type] = (cardTypes[type] || 0) + 1;
      
      // Show first few cards
      if (cardsSnapshot.size <= 5) {
        console.log(`   - ${doc.id}: ${type} (lane: ${card.lane || 'none'})`);
        if (card.content) {
          console.log(`     Content: ${JSON.stringify(card.content).substring(0, 100)}...`);
        }
      }
    });
    
    if (cardsSnapshot.size > 5) {
      console.log('\n   Card types:');
      Object.entries(cardTypes).forEach(([type, count]) => {
        console.log(`     - ${type}: ${count}`);
      });
    }
    console.log();
    
    // Check up_next
    const upNextSnapshot = await canvasRef.collection('up_next').get();
    console.log(`⏭️  Up Next: ${upNextSnapshot.size} items`);
    upNextSnapshot.forEach(doc => {
      const item = doc.data();
      console.log(`   - ${doc.id}: card_id=${item.card_id}, priority=${item.priority}`);
    });
    console.log();
    
    // Check recent events
    const eventsSnapshot = await canvasRef.collection('events')
      .orderBy('created_at', 'desc')
      .limit(10)
      .get();
    
    console.log(`📊 Recent Events (last 10):`);
    eventsSnapshot.forEach(doc => {
      const event = doc.data();
      const type = event.type || 'unknown';
      const created = event.created_at?.toDate?.() || event.created_at;
      
      if (type === 'agent_propose') {
        const cardIds = event.payload?.created_card_ids || [];
        const corrId = event.payload?.correlation_id || 'none';
        console.log(`   ✅ ${type} - created ${cardIds.length} cards (corr: ${corrId.substring(0, 8)}...)`);
      } else if (type === 'agent_publish_failed') {
        const error = event.payload?.error || 'unknown';
        console.log(`   ❌ ${type} - ${error}`);
      } else {
        console.log(`   📌 ${type}`);
      }
    });
    
    // Diagnosis
    console.log('\n' + '=' .repeat(60));
    console.log('🩺 DIAGNOSIS');
    console.log('=' .repeat(60));
    
    if (cardsSnapshot.size === 0) {
      console.log('⚠️  No cards in canvas - proposeCards likely never succeeded');
      console.log('   Possible causes:');
      console.log('   1. API key mismatch between agent and functions');
      console.log('   2. Missing X-User-Id header from agent');
      console.log('   3. Card validation failure in proposeCards');
      console.log('   4. Agent never called tool_canvas_publish');
    } else if (upNextSnapshot.size === 0) {
      console.log('⚠️  Cards exist but no up_next entries');
      console.log('   Cards may not be visible in UI');
    } else {
      console.log('✅ Canvas has cards and up_next entries');
      console.log('   If cards not showing in UI, check:');
      console.log('   1. iOS CanvasRepository subscription');
      console.log('   2. Card type mapping in iOS');
    }
    
  } catch (error) {
    console.error('❌ Error checking Firestore:', error.message);
  }
}

// Parse command line arguments
const args = process.argv.slice(2);
if (args.length < 2) {
  console.log('Usage: node check_firestore_canvas.js <userId> <canvasId>');
  console.log('Example: node check_firestore_canvas.js xLRyVOI0XKSFsTXSFbGSvui8FJf2 nF61JxsIgA2HOmDD1QsB');
  process.exit(1);
}

const [userId, canvasId] = args;
checkCanvas(userId, canvasId).then(() => process.exit(0));
