const { GoogleAuth } = require('google-auth-library');

// Initialize Google Auth for Vertex AI access
const auth = new GoogleAuth({
    scopes: ['https://www.googleapis.com/auth/cloud-platform']
});

// Vertex AI Configuration
const VERTEX_AI_CONFIG = {
    projectId: '919326069447',
    location: 'us-central1',
    agentId: '4683295011721183232',
    projectName: 'myon-53d85'
};

// ADK agents use v1 API endpoint
// Base URL for Vertex AI Agent Engine
const baseURL = `https://${VERTEX_AI_CONFIG.location}-aiplatform.googleapis.com/v1/projects/${VERTEX_AI_CONFIG.projectId}/locations/${VERTEX_AI_CONFIG.location}/reasoningEngines/${VERTEX_AI_CONFIG.agentId}`;

module.exports = {
    auth,
    VERTEX_AI_CONFIG,
    baseURL
}; 