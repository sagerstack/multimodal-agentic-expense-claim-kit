Mar 2026 51.511 Multimodal Generative AI Project Proposal  
Agentic Expense Claims - A Multi-Agent Multimodal System for Automated Expense Report Processing



Prepared by
Nguyen Thanh Tung (1011011)
Josiah Lau (1001530)
James Oon (TBD)
Sagar Pratap Singh (1010736)





















1.  Problem Decomposition

1.1  Problem Statement
The expense claim process at SUTD using SAP Concur contains operational inefficiencies for both students and administrative reviewers. Reimbursements may take up to two months due to multiple validation stages, manual data entry, policy interpretation challenges, and repeated claim resubmissions that often lead to errors and claim rejections.

1.2 Current Workflow Pain Points 
The current workflow faces several inefficiencies, including OCR errors in receipt extraction, time-consuming manual data entry, and complex policy rules with numerous GL codes. These issues frequently lead to claim rejections, require manual cross-checking of multimodal documents (receipts, PDFs, itineraries), and provide no real-time validation before submission.

1.3  Sub-Task Decomposition
The proposed workflow decomposes the process into four agent nodes orchestrated through a shared state: multimodal data extraction using vision-language models, policy compliance validation using retrieval-augmented reasoning, and parallel compliance and fraud detection checks. A final risk-based routing node aggregates the results and conditionally directs the claim toward automated approval, correction requests, or human review.
 
2  Agent Architecture
The system exposes a Chainlit-based conversational interface supporting two user personas:

Claimant persona- Interacts with the Intake Agent via image uploads and text input. The agent guides claim preparation, flags policy violations, and iterates until all pre-submission checks pass.

Reviewer persona- Receives escalated claims with the Advisor Agent's risk summary, compliance and fraud findings, and cited policy clauses. Can approve, reject, or return the claim with comments.
2.1  System Diagram

 
Figure 1 System diagram illustrating the stages in agentic expense workflow process, along with the respective agents, patterns and integration types

Figure 1 presents the system architecture as a four-agent pipeline orchestrated by LangGraph, with a clear boundary separating pre-submission and post-submission processing. During pre-submission stage, the Intake Agent guides the user (claimant) through receipt extraction and policy validation in a conversational loop. In the post-submission stage, the Compliance Agent and Fraud Agent assess the claim in parallel, and the Advisor Agent synthesizes their findings to auto-approve, return, or escalate the claim to the human reviewer based on established thresholds.
2.2  Agent Roles

The system is built on LangGraph, which acts as the multi-agent orchestrator, with each nodes hosting one or more agentic processes as part of the claim expense workflow:
Agent	Agentic Pattern	Serves	Responsibility
Intake Agent	ReAct + Evaluator Gate	Claimant	Guides the claimant through expense submission via a conversational loop. Extracts structured data from receipt images using a VLM, validates each item against policy rules, converts foreign currencies, and persists the finalized claim. Iterates with the claimant until all pre-submission checks pass.     
Compliance Agent	Evaluator	System	Audits the submitted claim against organizational-level policies that require context beyond the claimant's visibility: department budgets, cross-report spending limits, and approval thresholds. Produces a structured compliance finding with pass/fail per rule and cited policy clauses.
Fraud Agent	Tool call	System	Checks the submitted claim for fraudulent nature of receipts, anomaly detection or duplicate receipts by querying historical claims in the database. Returns a fraud/legit finding per receipt. 
Advisor Agent	Reflection + Routing	Reviewer	Synthesizes compliance and fraud findings into a risk assessment. Self-critiques its reasoning via reflection, then routes the claim to one of three outcomes: auto-approve, return to claimant with correction instructions, or escalate to a human reviewer with a summary and policy citations.                                                     
2.3  Model and Tool Choices

Orchestration: LangGraph. The workflow requires conditional branching (Evaluator gate in Intake), parallel execution (Compliance and Fraud), loops (ReAct iteration), and state passing between agents. LangGraph models these as a state machine with explicit graph nodes and edges, providing deterministic control flow. Each agent is a graph node — a Python function that reads shared state, invokes the LLM with tools as needed, and returns updated state. No additional agentic SDK is required; LangGraph natively supports ReAct via create_react_agent, routing via conditional edges, and parallelization via fan-out/fan-in.

Vision-Language Model: GLM-4.6V. Receipt extraction requires grounding structured fields (merchant, date, amount, currency, line items) from images with varying quality — crumpled receipts, poor lighting, mixed languages. GLM-4.6V is a Mixture-of-Experts VLM with flexible thinking modes, well-suited for
complex document analysis requiring deep reasoning and context understanding. It processes receipt images natively without a separate OCR-then-parse pipeline, reducing error propagation.

LLM for reasoning agents: GLM-5. The Compliance, Fraud, and Advisor agents require text-based reasoning over structured data and policy documents. GLM-5 serves as the backbone LLM for all reasoning nodes. The Intake Agent's conversational loop has the tightest latency requirement since it is user-facing.

MCP Servers


MCP Server	Used By	Purpose
RAG MCP
(rag-mcp-server)	Intake Agent, 
Compliance Agent	Retrieves relevant policy clauses from institutional knowledge base 
DBHub MCP	Intake Agent,
Fraud Agent	Provides database access via Postgres to retrieve and store structured data (save expense claims, retrieve historical claims)
Frankfurter MCP	Intake Agent	Converts foreign currency amounts to SGD using live exchange rates
Email MCP	Advisor Agent	Sends notification emails to claimants (returns, status updates), and reviewers (escalations) 

3  Multimodal Grounding
3.1  Modalities Used
[TODO] At least two modalities — describe each:
•	Image: Receipt photos, scanned documents (processed by VLM)
•	Text: Policy documents, claim descriptions, reviewer notes (processed by LLM + RAG)
•	Structured data: Database records, credit card feeds, budget tables (accessed via MCP/DB)
3.2  Cross-Modal Interaction
[TODO] Explain how modalities interact within the agent system:
•	VLM extracts structured fields from receipt images -> LLM validates against text policy via RAG
•	Image forensics output (Fraud Agent) combined with structured DB history for risk scoring
•	Compliance Agent cross-references extracted image data with database records and policy text


        Figure X: Agentic Multimodal Expense Claims Processing Workflow
3.1 Modalities Used

The system processes three distinct modalities to enable comprehensive expense claim validation:
Image Modality (Receipt Processing)
Receipt images uploaded by claimants serve as the primary evidence for expense claims. These images include:
1.	Photographs captured via mobile devices (varying lighting, angles, quality)
2.	Scanned PDF documents from desktop uploads
3.	Screenshots of digital receipts from e-commerce platforms
4.	Multi-page invoices with itemized breakdowns

The Vision-Language Model (VLM) processes these images to extract structured fields including merchant name, transaction date, total amount, currency, tax breakdown, itemized line items, and payment method. Image quality varies significantly in real-world usage—receipts may be crumpled, faded, partially occluded, or captured under poor lighting conditions. The VLM must handle these variations while providing confidence scores for each extracted field.
Text Modality (Policy and Contextual Information)
Text-based information flows through the system in multiple forms:
1.	Policy documents: SUTD expense reimbursement policies, GL code definitions, per-diem rates, category-specific rules (e.g., meal caps, transport allowances)
2.	Claimant descriptions: Free-text explanations provided by users describing the business purpose of each expense
3.	Historical claim notes: Reviewer feedback from previous submissions, rejection reasons, correction instructions
4.	Itineraries and supporting documents: Travel schedules, conference agendas, meeting invitations

Large Language Models (LLMs) with Retrieval-Augmented Generation (RAG) process this text modality. The RAG pipeline embeds policy documents into a vector database, retrieves relevant clauses based on the claim context, and applies them to validate compliance. This approach is essential because policies are updated periodically, and rules are often conditional (e.g., "meals during overseas travel may exceed the standard cap if justified").
Structured Data Modality (Database and Financial Records)
The system accesses structured data from institutional databases and external APIs:
1.	Historical claim database: Past submissions by the same claimant (merchant patterns, spending trends, approval history)
2.	Credit card feeds: Corporate card transactions for cross-validation
3.	Budget and project codes: Departmental budget limits, project-specific allocations, GL code hierarchies
4.	Currency exchange rates: Real-time and historical forex data via Frankfurter API to validate multi-currency claims
5.	Vendor registries: Approved merchant lists, blacklisted vendors, fraud databases
This modality is accessed through MCP (Model Context Protocol) servers that provide tool-calling interfaces for SQL queries, API lookups, and data aggregation.
3.2 Cross-Modal Interaction
Multimodal grounding is achieved through structured cross-modal reasoning at each agent stage:
Stage 1: Image-to-Text Grounding (Intake Agent)
The Intake Agent first processes the receipt image using a VLM to extract a structured JSON representation. This output is then grounded against the claimant's text description to detect inconsistencies. For example:
1.	If the VLM extracts "Merchant: Starbucks, Amount: $45.00" but the claimant description states "taxi fare to airport," the system flags a mismatch.
2.	If the receipt date is extracted as "2024-03-15" but the claimed trip itinerary (text) indicates travel occurred in February, a temporal inconsistency is raised.
Confidence scores from the VLM are used to trigger clarification requests. Low-confidence fields prompt the agent to ask the user: "We detected the amount as $12.50 with 68% confidence. Please confirm or correct this value."
Stage 2: Text-to-Structured Data Grounding (Compliance Agent)
The Compliance Agent grounds policy text against both extracted image data and database records. For instance:
1.	Policy retrieval: The system embeds the claim context ("meal expense, overseas trip, Japan, $85") and retrieves the relevant policy clause: "Meal allowance for overseas travel: up to $50 per day unless justified by group dining."
2.	Cross-modal validation: The VLM-extracted receipt shows a restaurant name and 4 itemized meals. The agent cross-references this image evidence with the text justification ("team dinner with collaborators") and database records (checking if the trip was approved, if other team members filed similar claims).
3.	Compliance decision: If the receipt shows 4 meals and the text describes a group event, the claim may be approved despite exceeding the standard cap. If the receipt shows 1 meal for $85, the system flags it for review.
Stage 3: Image Forensics + Structured Data (Fraud Agent)
The Fraud Agent performs cross-modal fraud detection:
1.	Image forensics: Analyzes the receipt image for signs of manipulation (JPEG artifacts, clone-stamping, text layer inconsistencies) using specialized forensics tools.
2.	Database comparison: Checks if the same receipt image (or perceptually similar image) has been submitted before by this or other claimants.
3.	Pattern analysis: Compares the current claim against structured historical data—if a claimant suddenly files 5 high-value meal claims in one week after months of minimal activity, the pattern is flagged.
4.	Multi-source agreement: If image forensics suggests tampering but the merchant exists in verified vendor databases and the amount matches credit card records, the system may downweight the fraud signal.

Stage 4: Aggregated Multi-Modal Decision (Advisor Agent)
The Advisor Agent synthesizes outputs from all modalities:
1.	VLM confidence scores (image modality)
2.	Policy compliance reasoning (text modality via RAG)
3.	Fraud risk scores (structured data + image forensics)
4.	Agent disagreement signals (e.g., Compliance says "approve" but Fraud says "suspicious")

The Advisor uses a reflection step to ensure its recommendation is supported by evidence across modalities. For example:
1.	If all modalities align (clear receipt image, policy-compliant, no fraud signals, no agent disagreement), the claim is auto-approved.
2.	If the VLM extraction has low confidence (image quality issue), even if policy compliance is satisfied, the claim is returned to the claimant for a clearer upload.
3.	If fraud detection flags a duplicate receipt but compliance and extraction are otherwise valid, the system escalates to human review with full cross-modal evidence.
This cross-modal interaction ensures that no single modality dominates decision-making, and uncertainty in one modality triggers appropriate handling strategies rather than silent failures
4  Control and Failure Handling
4.1  Error Detection Mechanisms
Our system detects uncertainty at each agent stage rather than treating expense claims as a single end-to-end prediction. In pre-submission, the Intake Agent uses ReAct + evaluator gate with the VLM, RAG MCP, Frankfurter MCP, and DBHub MCP to extract receipt data, retrieve policy context, convert currency, and store the claim. It checks for unreadable receipts, missing fields, inconsistent values, and unsupported drafts; low-confidence claims are returned to the claimant. After submission, the Compliance Agent and Fraud Agent run in parallel. The Compliance Agent uses RAG MCP with an evaluator-optimizer pattern to check policy rules, budgets, and approval conditions. The Fraud Agent uses DBHub MCP with prompt chaining for duplicate-check screening. Finally, the Advisor Agent performs reflection + routing, combines both outputs, cites policy clauses, and routes the claim to auto-approve, return to claimant, or escalate to reviewer.4.2  Retry, Self-Critique, and Fallback Strategies
Each agent includes bounded retry and conservative fallback. The Intake Agent may retry extraction or retrieval, but if the claim remains incomplete it is returned to the claimant. The Compliance Agent refines its assessment through an evaluator-optimizer loop until the case is clearly compliant, non-compliant, or no longer improving. The Fraud Agent raises a red flag only when duplicate evidence is strong; otherwise it passes forward uncertainty. The Advisor Agent reflects before final routing so automation is used only when evidence is sufficient. If tools fail, the system degrades gracefully: failed VLM extraction triggers resubmission, weak RAG support leads to conservative routing, and unresolved DBHub checks are treated as uncertain rather than clean.
5  Evaluation Strategy (Preliminary)
5.1  Task-Specific Success Criteria
Metric	Target	Measurement Method
Submission time	< 3 min (vs. 15-25 min)	The average time from receipt upload to completed claim submission during a controlled user study with students submitting sample claims.
Accuracy	> 95% on structured fields	Evaluate field-level accuracy
5.2  Baselines We evaluate the proposed system against general-purpose baselines (GPT-5.4 and Gemini 1.5 Pro with a ReAct agentic framework) to determine whether the agentic architecture improves extraction accuracy, automation rate, and overall workflow efficiency.
5.3  Failure Analysis - System limitations are analyzed using four methods: self-consistency checks across runs, cross-modal agreement checks, verifier models for independent validation, and disagreement analysis between agents. These help identify errors in extraction, policy reasoning, and agent coordination.
6  Reflection (Preliminary)
6.1  When Agentic Behavior is Beneficial - Agentic behavior adds value because expense claim processing requires coordinated reasoning across multimodal inputs (receipts, PDFs, and policy text) and multiple steps such as extraction, policy validation, and compliance checking, which are difficult to handle reliably with a single-model or rule-based workflow.
6.2  Limitations -The proposed approach may face limitations due to OCR inaccuracies, evolving policy rules that require continuous updates, increased system complexity from multi-agent coordination, and the need for human oversight in ambiguous or high-risk claims.
References
[TODO] Add references. Not counted toward 3-page limit.
