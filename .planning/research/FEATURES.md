# Feature Landscape

**Domain:** AI-powered expense claims/management system
**Researched:** 2026-03-23
**Confidence:** HIGH

## Table Stakes

Features users expect from AI-powered expense systems. Missing these = system fails its purpose.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Receipt OCR extraction** | Core value prop - eliminates manual data entry. Industry standard with 95-99% accuracy. | Medium | VLM-based OCR achieves 97-99% vs 64% for traditional pattern matching. Must extract merchant, date, amount, line items, tax. |
| **Real-time policy validation** | Users expect instant feedback on compliance before submission, not post-submission rejection. | Medium | Validates against budgets, spending limits, category restrictions. Pre-submission reduces back-and-forth by ~40%. |
| **Duplicate detection** | Prevents fraud and honest mistakes. Expected in any modern expense system. | Low-Medium | Match on date + amount + currency. Advanced: receipt image hashing, fuzzy vendor matching. |
| **Currency conversion** | Essential for international organizations. Prevents costly manual conversion errors. | Low | Auto-detect currency from receipt, apply correct conversion rate, store original and converted amounts. |
| **Multi-language receipt support** | Organizations operate globally. Receipts come in many languages. | Medium | Leading systems support 32-42 languages. Must translate for policy validation while preserving original. |
| **Approval workflow** | Human-in-the-loop for escalated/flagged claims. Cannot be fully autonomous in 2026. | Low-Medium | Risk-based routing: auto-approve low-risk, escalate high-risk or policy violations. |
| **Audit trail** | Regulatory requirement. Must track all actions, decisions, state changes. | Low | Who did what when. Immutable log for compliance and dispute resolution. |
| **Conversational UI for claimants** | Users expect natural interaction, not form-filling. Industry shifted from forms to chat. | Medium | Guides submission, answers questions, prompts for missing info. Reduces submission time from 15-25 min to <3 min. |

## Differentiators

Features that set a multi-agent AI approach apart. Not universally expected, but create competitive advantage.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Multi-agent architecture** | Specialized agents (intake, compliance, fraud, advisor) provide deeper analysis than monolithic AI. | High | Allianz's Nemo system: 7 agents process claims in <5 min. Each agent owns a narrow skill. Industry trend for 2026. |
| **Pre-submission fraud detection** | Catches issues BEFORE submission, not after. Proactive vs reactive. | High | Analyzes receipt authenticity (AI-generated, altered images), behavioral patterns, contextual anomalies. Deepfake incidents increased 700% in 2023. |
| **AI-generated receipt detection** | Emerging threat in 2026. Most systems don't detect this yet. | High | Analyzes image metadata (EXIF), grayscale patterns, copy-move detection. Deloitte estimates $11.5B fraud losses by 2027. |
| **Conversational advisor agent** | Synthesizes findings from multiple agents into clear guidance for users and reviewers. | Medium-High | Goes beyond "approved/rejected" - explains why, suggests fixes, educates on policy. |
| **Behavioral pattern analysis** | Learns normal spending per employee/department, flags statistical deviations. | High | More sophisticated than rule-based. Detects novel fraud patterns. Requires historical data. |
| **100% automated audit** | Every claim analyzed by AI, not sample-based. Zero-touch for compliant claims. | Medium-High | Brex processes 99% of expense reports without human involvement. Industry milestone for 2026. |
| **Multi-turn conversational loop** | Handles clarifications, missing receipts, policy questions within one conversation. | Medium | Reduces context switching. User stays in chat, doesn't email finance team separately. |
| **Explainable AI decisions** | Shows reasoning for flagged claims, policy violations, risk scores. | Medium | Builds trust. Required for human reviewers to override AI decisions confidently. |

## Anti-Features

Features to explicitly NOT build for a course project. Common mistakes or scope creep.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **Travel booking integration** | Out of scope. SAP Concur's focus, but not core to expense claims processing. | Focus on expense claim workflow only. Assume travel already booked externally. |
| **Corporate card issuance** | Brex/Ramp territory. Requires banking license, payment processing infrastructure. | Accept all payment methods. Focus on claim validation, not card provisioning. |
| **Accounting system integration** | Complex, vendor-specific. Course project doesn't need QuickBooks/Xero/SAP ERP sync. | Export to CSV/JSON. Prove the AI pipeline works, not enterprise integration. |
| **Mobile app** | Doubles development effort. Not necessary to prove multi-agent value. | Web UI only (Chainlit). Mobile receipt upload via web works fine. |
| **Reimbursement payment processing** | Requires bank integration, ACH/wire transfers, compliance. | End workflow at "approved for payment". Don't actually transfer funds. |
| **Multi-tenant SaaS** | Course project serves one org (SUTD). Multi-tenancy adds database, security, UX complexity. | Single-tenant. Hardcode SUTD policies in config, not UI for policy management. |
| **Advanced reporting/analytics** | Dashboard building is scope creep. Not core to AI agent value prop. | Provide basic claim history view. Focus effort on agent intelligence, not BI tools. |
| **Vendor management** | Tracking vendor contracts, negotiating rates (Ramp's focus). Orthogonal to claim processing. | Assume vendors exist. Extract vendor name from receipt, don't manage vendor lifecycle. |
| **Budgeting tools** | Separate finance function. Expense systems check budgets, don't create them. | Read budget limits from config. Don't build budget creation/allocation UI. |
| **Real-time notifications** | Email/SMS/Slack alerts add infrastructure (SMTP, Twilio, webhooks). Diminishing returns. | In-app status updates only. User checks Chainlit chat for claim status. |

## Feature Dependencies

```
Receipt Upload
    └─> OCR Extraction (Intake Agent)
            ├─> Currency Conversion
            ├─> Policy Validation (Compliance Agent)
            │       └─> Budget Checks
            │       └─> Category/Limit Rules
            ├─> Fraud Detection (Fraud Agent)
            │       └─> Duplicate Detection
            │       └─> AI-Generated Receipt Detection
            │       └─> Behavioral Analysis (optional - requires history)
            └─> Advisor Agent Synthesis
                    └─> Approval Routing
                            ├─> Auto-approve (low risk, compliant)
                            └─> Human Review (escalated)
                                    └─> Audit Trail

Conversational UI spans all steps (multi-turn loop for clarifications)
```

**Critical path for MVP:**
1. Receipt Upload → OCR → Policy Validation → Approval Routing
2. Conversational UI for claimant persona
3. Duplicate detection (prevents obvious fraud)
4. Audit trail (proves decisions are traceable)

**Can defer:**
- Behavioral pattern analysis (requires historical data, complex ML)
- AI-generated receipt detection (advanced, lower ROI for course project)
- Multi-language support beyond English (nice-to-have, not critical for SUTD)

## MVP Recommendation

For a course project demonstrating multi-agent AI value in <3 months:

### Must Build (Core Differentiation)
1. **Multi-agent pipeline**: Intake → Compliance → Fraud → Advisor (proves architecture)
2. **VLM receipt extraction**: Merchant, date, amount, line items (table stakes + technical showcase)
3. **Real-time policy validation**: Budget limits, category rules, spending thresholds (table stakes)
4. **Duplicate detection**: Hash-based + fuzzy matching (table stakes fraud prevention)
5. **Conversational UI (claimant)**: Chainlit chat for submission + status (UX differentiator)
6. **Approval routing with explanation**: Auto-approve vs escalate with reasoning (explainable AI)
7. **Audit trail**: Logs all agent decisions, state changes (compliance table stakes)
8. **Reviewer UI**: Simple interface for processing escalated claims (human-in-the-loop)

### Should Build (High Value, Moderate Complexity)
9. **Currency conversion**: Auto-detect and convert foreign receipts (table stakes for international org)
10. **Multi-turn conversation**: Handle missing receipts, clarifications in one session (UX polish)
11. **Risk scoring**: Assign 0-100 risk score to each claim for prioritization (fraud agent output)

### Nice-to-Have (Defer if Time-Constrained)
- Behavioral pattern analysis (requires seeding historical data, complex)
- AI-generated receipt detection (cutting-edge but high complexity/low demo value)
- Multi-language OCR (English-only sufficient for MVP)
- Advanced fraud patterns (focus on duplicates + simple rules first)

### Explicitly Exclude
- Travel booking, corporate cards, payment processing, mobile app, multi-tenant SaaS, vendor management, budgeting tools, BI dashboards (per anti-features)

## Success Metrics Alignment

Course project goal: **Reduce submission time from 15-25 min to <3 min with >95% extraction accuracy.**

| Feature | Metric Impact |
|---------|---------------|
| VLM OCR extraction | **>95% accuracy** (directly measured) |
| Conversational UI | **<3 min submission** (eliminates form-filling) |
| Real-time policy validation | **<3 min submission** (prevents post-submission rework) |
| Multi-agent architecture | **Quality** (demonstrates specialized agents > monolithic AI) |
| Auto-approval for low-risk | **<3 min end-to-end** (no waiting for reviewer) |
| Explainable decisions | **Trust/adoption** (users understand AI reasoning) |

**Trade-off for course project:**
- Optimize for **demo-ability** (show agents working together visually in Chainlit)
- Optimize for **differentiation** (multi-agent is the research contribution)
- De-prioritize **enterprise features** (integrations, multi-tenancy, mobile, payments)

## Sources

### AI-Powered Expense Management (2026)
- [8 Ways AI Improves Expense Management in 2026 - Navan](https://navan.com/blog/ai-expense-management)
- [AI Expense Management: Full Guide (2026) - Articsledge](https://www.articsledge.com/post/ai-expense-management)
- [Emburse Releases AI-Powered Expense Compliance Solution - CPA Practice Advisor](https://www.cpapracticeadvisor.com/2026/02/17/emburse-releases-ai-powered-expense-compliance-solution/178189/)
- [Zero-Touch Expense Reporting in 2026 - Expense Anywhere](https://expenseanywhere.com/zero-touch-expense-reporting-ai-automated-expense-management-2026/)
- [How AI Transforms Expense Management - Ramp](https://ramp.com/blog/ai-expense-management)

### OCR & Receipt Extraction
- [How OCR Receipt Scanning Works - Doxbox](https://doxbox.io/blog/how-ocr-receipt-scanning-works-expense-claims)
- [The Best Receipt OCR Software for 2026 - Klippa](https://www.klippa.com/en/ocr/financial-documents/receipts/)
- [Receipt Scanning in Expense Management - Ramp](https://ramp.com/blog/receipt-scanning-expense-management)

### Fraud Detection & Compliance
- [Emburse AI Compliance Solution - CPA Practice Advisor](https://www.cpapracticeadvisor.com/2026/02/17/emburse-releases-ai-powered-expense-compliance-solution/178189/)
- [AI Fraud Detection in Banking 2026 - Emburse](https://www.emburse.com/resources/ai-fraud-detection-in-banking)
- [AI Expense Audit Software - AppZen](https://www.appzen.com/ai-for-expense-audit)
- [Expense Fraud: How to Identify and Prevent - Rydoo](https://www.rydoo.com/cfo-corner/expense-fraud-companies/)

### Multi-Agent AI Architecture
- [Agentic AI in Financial Services - AWS](https://aws.amazon.com/blogs/industries/agentic-ai-in-financial-services-choosing-the-right-pattern-for-multi-agent-systems/)
- [AI Agent Technical Architecture in Payment Systems - IntellectyX](https://www.intellectyx.com/ai-agent-technical-architecture-in-financial-payment-systems-for-real-time-fraud-detection/)
- [Allianz First Agentic AI for Claims Automation](https://www.allianz.com/en/mediacenter/news/articles/251103-when-the-storm-clears-so-should-the-claim-queue.html)
- [Deploying Agentic AI for Insurance Fraud Detection - AltaWorld](https://altaworld.tech/deploying-agentic-ai-for-insurance-frauddetection-a-practical-look/)

### Feature Comparisons
- [Top 7 SAP Concur Competitors - Brex](https://www.brex.com/spend-trends/expense-management/concur-competitors-and-alternatives)
- [Top 8 SAP Concur Alternatives - Ramp](https://ramp.com/blog/top-concur-alternatives)
- [Expensify vs Concur Comparison - Expensify](https://use.expensify.com/resource-center/guides/expensify-vs-concur-comparison)
- [Expensify vs SAP Concur - Ramp](https://ramp.com/blog/expensify-vs-concur)

### Expense Management Best Practices & Anti-Patterns
- [Expense Management Trends for 2026 - American Express](https://www.americanexpress.com/en-us/business/trends-and-insights/articles/expense-management-trends-for-2026/)
- [Biggest Spend Management Mistakes to Avoid - Extend](https://www.paywithextend.com/resource/biggest-spend-management-mistakes-to-avoid)
- [Employee Expense Best Practices for 2026 - DATABASICS](https://blog.data-basics.com/employee-expense-spend-management-best-practices-for-2026)
- [Six Most Common Expense Management Issues - Rolling Arrays](https://rollingarrays.com/blogs/the-six-most-common-expense-management-issues-and-how-to-fix-them/)

### Duplicate Detection & Currency Conversion
- [Duplicate Expense Detection - Zoho](https://www.zoho.com/us/expense/kb/admin/expenses/detect-duplicates/)
- [What is Duplicate Expense Detection - Navan](https://navan.com/resources/glossary/what-is-duplicate-expense-detection)
- [How to Spot Fake Receipts - Resistant AI](https://resistant.ai/blog/how-to-spot-fake-receipts)
- [Detection of Duplicate Expenses - Oracle](https://docs.oracle.com/en/cloud/saas/financials/24c/fawde/detection-of-duplicate-expenses.html)
