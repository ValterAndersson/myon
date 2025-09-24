# Multi-Agent Catalog Curation System

A sophisticated, autonomous system for managing and curating the exercise catalog using multiple specialized AI agents coordinated by a central orchestrator.

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      ORCHESTRATOR                            │
│  (Central coordinator - manages all agents & workflows)      │
└────────────────┬────────────────────────────────────────────┘
                 │
    ┌────────────┼────────────┬─────────────┬────────────┐
    │            │            │             │            │
┌───▼───┐  ┌────▼────┐  ┌────▼────┐  ┌────▼────┐  ┌────▼────┐
│TRIAGE │  │ENRICHMENT│  │ JANITOR │  │  SCOUT  │  │ AUDITOR │
│Agent  │  │  Agent   │  │  Agent  │  │  Agent  │  │  Agent  │
└───┬───┘  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘
    │           │            │             │            │
    └───────────┴────────────┴─────────────┴────────────┘
                            │
                    ┌───────▼────────┐
                    │ Firebase       │
                    │ Functions      │
                    │ (Catalog API)  │
                    └────────────────┘
```

## 🤖 Agent Roles

### 1. **Orchestrator** (Brain)
- **Purpose**: Central coordinator that manages all agents
- **Intelligence**: High-reasoning LLM
- **Responsibilities**:
  - Assess catalog state
  - Dispatch work to specialized agents
  - Manage parallelism and dependencies
  - Handle errors and retries
  - Generate reports

### 2. **Triage Agent** (Normalizer)
- **Purpose**: Assign family_slug and variant_key to exercises
- **Frequency**: Every 15 minutes
- **Intelligence**: Low-cost/specialized model
- **Key Actions**:
  - Find unnormalized exercises
  - Suggest appropriate categorization
  - Apply normalization

### 3. **Enrichment Agent** (Enhancer)
- **Purpose**: Add aliases to improve searchability
- **Frequency**: Daily
- **Intelligence**: High-reasoning LLM
- **Key Actions**:
  - Generate alias suggestions
  - Create shorthand versions
  - Add common misspellings

### 4. **Janitor Agent** (Deduplicator)
- **Purpose**: Merge duplicate exercises within families
- **Frequency**: Weekly
- **Intelligence**: Low-cost model (tool does heavy lifting)
- **Key Actions**:
  - Identify duplicates
  - Merge exercises
  - Preserve historical data

### 5. **Scout Agent** (Gap Finder) [Coming Soon]
- **Purpose**: Create new exercises from failed searches
- **Frequency**: Hourly
- **Intelligence**: Mixed (analysis + creation)
- **Key Actions**:
  - Analyze search logs
  - Identify missing exercises
  - Create draft entries

### 6. **Auditor Agent** (Quality Inspector) [Coming Soon]
- **Purpose**: Audit catalog for systemic issues
- **Frequency**: Weekly
- **Intelligence**: High-reasoning LLM
- **Key Actions**:
  - Run dry-run normalizations
  - Generate quality reports
  - Flag issues for review

## 🚀 Quick Start

### Prerequisites
```bash
pip install -r requirements.txt
```

### Run the Demo
```bash
python demo.py
```

### Run the Orchestrator Once
```bash
python test_orchestrator.py
```

### Start the Scheduler (Daemon Mode)
```bash
python scheduler.py --mode daemon
```

### Run Specific Agent
```bash
python scheduler.py --mode once --agent TRIAGE
```

## 📁 Project Structure

```
multi_agent_system/
├── orchestrator/
│   └── orchestrator.py      # Main orchestrator logic
├── agents/
│   ├── triage_agent.py      # Exercise normalization
│   ├── enrichment_agent.py  # Alias generation
│   └── janitor_agent.py     # Deduplication
├── config/
│   └── production_config.json # Production settings
├── logs/                     # Execution logs & reports
├── scheduler.py              # Scheduling system
├── demo.py                   # Interactive demo
├── test_orchestrator.py      # Test script
└── deploy.sh                 # Cloud deployment script
```

## 🔧 Configuration

Edit `config/production_config.json` to customize:

- **Agent Settings**: Batch sizes, parallelism, retries
- **Schedules**: Frequency and timing of each agent
- **Monitoring**: Alerts, metrics, thresholds
- **Firebase**: Rate limits, retry policies

## 📊 Monitoring & Logs

### View Logs
```bash
tail -f logs/orchestrator_$(date +%Y%m%d).log
```

### Check Agent Status
```bash
python scheduler.py --mode status
```

### View Reports
```bash
ls -la logs/report_*.json
```

## 🚢 Deployment

### Deploy to Cloud Run
```bash
chmod +x deploy.sh
./deploy.sh
```

### Environment Variables
- `MYON_FUNCTIONS_BASE_URL`: Firebase functions endpoint
- `FIREBASE_API_KEY`: API key for Firebase functions
- `CATALOG_ADMIN_ENGINE_ID`: Vertex AI agent engine ID

## 📈 Metrics & KPIs

The system tracks:
- **Processing Rate**: Exercises processed per hour
- **Normalization Rate**: % of exercises with family/variant
- **Approval Rate**: % of exercises approved
- **Alias Coverage**: Average aliases per exercise
- **Deduplication Impact**: Duplicates merged per week
- **Error Rate**: Failed operations per agent

## 🔄 Workflow Example

1. **Assessment** (Every 5 min)
   - Orchestrator queries catalog state
   - Identifies work needed

2. **Triage** (Every 15 min)
   - Process unnormalized exercises
   - Assign family and variant

3. **Enrichment** (Daily)
   - Add aliases to normalized exercises
   - Improve searchability

4. **Deduplication** (Weekly)
   - Merge duplicates within families
   - Clean up catalog

5. **Audit** (Weekly)
   - Generate quality report
   - Flag issues for human review

## 🎯 Future Enhancements

- [ ] **Scout Agent**: Mine search logs for gaps
- [ ] **Auditor Agent**: Deep quality analysis
- [ ] **Prophet Agent**: Predictive exercise suggestions
- [ ] **Validator Agent**: Rule-based invariant checking
- [ ] **Historian Agent**: Time-travel debugging
- [ ] **Vector Embeddings**: Similarity-based operations
- [ ] **A/B Testing**: Compare agent strategies
- [ ] **Cost Optimization**: Dynamic model selection

## 🤝 Contributing

1. Test changes locally with `demo.py`
2. Update tests in `test_orchestrator.py`
3. Document new agents in this README
4. Update production config if needed

## 📝 License

Proprietary - MYON Fitness Technology

## 🆘 Troubleshooting

### Agent Fails Repeatedly
- Check logs in `logs/` directory
- Verify Firebase API key is correct
- Check rate limits aren't exceeded

### Orchestrator Can't Connect
- Verify Vertex AI agent is deployed
- Check network connectivity
- Validate credentials

### Scheduler Not Running
- Ensure `schedule` package is installed
- Check no other instance is running
- Verify config file exists

## 📞 Support

For issues or questions, check the logs first, then contact the development team.
