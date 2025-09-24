const admin = require('firebase-admin');
const axios = require('axios');

if (!admin.apps.length) {
  admin.initializeApp();
}

const db = admin.firestore();

async function publishWeeklyGroup({ apiBase, apiKey, userId, canvasId, weekId, vizDatasetRef, summaryBullets }) {
  const url = `${apiBase}/proposeCards`;
  const headers = { 'X-API-Key': apiKey, 'X-User-Id': userId };
  const groupId = `weekly_progress_${weekId}`;

  const cards = [
    {
      type: 'proposal_group',
      meta: { groupId },
      content: { groupId, title: 'Weekly Progress' },
      lane: 'analysis',
      priority: 80,
      ttl: { minutes: 20160 }
    },
    {
      type: 'summary',
      lane: 'analysis',
      refs: { topic_key: `weekly:${weekId}` },
      meta: { groupId },
      content: { title: 'Weekly Progress', bullets: summaryBullets || [] },
      priority: 79,
      ttl: { minutes: 20160 }
    },
    {
      type: 'visualization',
      lane: 'analysis',
      refs: { topic_key: `weekly:${weekId}` },
      meta: { groupId },
      content: {
        chart_type: 'line',
        spec_format: 'vega_lite',
        spec: {},
        dataset_ref: vizDatasetRef || null
      },
      priority: 78,
      ttl: { minutes: 20160 }
    }
  ];

  const payload = { canvasId, cards };
  const res = await axios.post(url, payload, { headers });
  return res.data;
}

module.exports = { publishWeeklyGroup };



