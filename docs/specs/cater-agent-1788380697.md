# Feature Specification: Catering Agent (`cater_agent`) & Preference Memory Integration

## 1. Feature Overview & Objectives
The Luncher multi-agent orchestration system coordinates strategy-aligned team lunch meetings by delegating tasks across specialized sub-agents. This specification defines the integration of a dedicated **Catering Agent** (`cater_agent`) to suggest curated, thematic 4-course catering menus pulled from enterprise catering data (BigQuery via MCP) and to record and honor team members' dietary preferences, allergies, likes, and dislikes using persistent agentic memory storage.

### Primary Objectives
- **Dynamic Catering Menus**: Present 3 distinct, thematic catering menus for any planned lunch meeting. Each menu consists of 1–3 main dishes, 2–3 side dishes, beverages, and desserts.
- **Dietary Restriction Filtering**: Automatically consult team dietary memories prior to menu generation and filter out any items containing allergens or conflicting ingredients.
- **Team Dietary Memory Management**: Enable users to record allergies, dietary preferences (e.g., vegan, gluten-free, halal), likes, and dislikes per team member or for the team as a whole, persisted to Memory Bank (when deployed to Agent Runtime) or local memory store (when running locally).
- **End-to-End Booking Integration**: Store the selected catering menu alongside meeting schedule details in the unified booking record.
- **Cross-Environment Resilience**: Connect to BigQuery catering menu data via BigQuery MCP with graceful fallback to local menu dataset when offline or unauthenticated.

---

## 2. User Personas & Core Journeys

### User Personas
- **Meeting Organizer**: Plans team strategy lunches, reviews proposed thematic menus, and selects a catering option that fits all attendees' dietary needs.
- **Team Member**: Shares personal dietary constraints (e.g., "Alice is allergic to shellfish and peanuts", "Bob prefers plant-based meals") so future lunch proposals automatically accommodate them.

### Core User Journeys
1. **Lunch Planning with Catering Suggestions**:
   - User requests: *"Plan a lunch meeting for the launch team next Tuesday."*
   - System analyzes strategic alignment (`strat_agent`), identifies mutual availability (`sched_agent`), queries catering data respecting active dietary preferences (`cater_agent`), and synthesizes 3 ranked time slots paired with 3 thematic catering menus.
2. **Dedicated Dietary Preference Update**:
   - User inputs: *"Carol is vegetarian and Dan cannot eat dairy."*
   - System recognizes dietary preference update, records memories in team memory store, confirms the update, and invites future scheduling without triggering an unwanted booking workflow.
3. **Combined Planning & Dietary Update**:
   - User inputs: *"Schedule lunch for Friday, and note that Eve is gluten-free."*
   - System records the new preference into memory and immediately generates lunch proposals with 100% gluten-safe catering menus.
4. **Meeting Selection & Menu Confirmation**:
   - User inputs: *"Let's go with Slot 1 and Menu 2 (Mediterranean Delight)."*
   - System confirms the booking and saves the complete meeting record including chosen time slot, rationale, and selected catering menu details.

---

## 3. Key Product Decisions & User Feedback
The following architectural and product choices were established during proactive stakeholder alignment:

1. **Dedicated Preference Routing**:
   - Prompts that solely state dietary preferences (e.g., *"Alice is allergic to peanuts"*) are routed directly to memory persistence. The system confirms the memory update and appends an invitation for future lunch planning without triggering booking operations.
   - Prompts combining preferences with planning (e.g., *"Plan lunch for Wednesday, Bob is dairy-free"*) persist the preference first, then proceed immediately to generate lunch and menu proposals respecting the newly added constraint.
2. **Unified Booking Record**:
   - When a user confirms a meeting and selects a catering menu, the selected menu structure (theme name, main dishes, sides, beverage, dessert) is persisted directly within the shared booking record alongside `time_slot`, `reason`, and `booking_id`.
3. **Hybrid MCP with Local Dataset Fallback**:
   - `cater_agent` accesses BigQuery `catering.menu_items` via BigQuery MCP `execute_sql`. In local offline or unauthenticated environments where the MCP server is unavailable, the agent gracefully falls back to querying the local catering dataset to ensure zero developer disruption.
4. **Standard Menu Composition**:
   - Every proposed menu must strictly conform to the 4-course structure: 1–3 main dishes, 2–3 sides, beverage(s), and dessert(s), organized under an overarching culinary theme (e.g., *Italian Trattoria*, *Pan-Asian Bistro*, *Baja Fiesta*).

---

## 4. Domain Models & Data Contracts

### 4.1 Dietary Preference Record
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "DietaryPreference",
  "type": "object",
  "properties": {
    "person_name": { "type": "string", "description": "Name of team member or 'team' for collective preferences" },
    "preference_type": { "type": "string", "enum": ["allergy", "restriction", "dislike", "like"] },
    "details": { "type": "string", "description": "Specific ingredient or food category (e.g., peanuts, shellfish, vegan, dairy)" },
    "created_at": { "type": "string", "format": "date-time" }
  },
  "required": ["person_name", "preference_type", "details"]
}
```

### 4.2 Catering Menu Item & Thematic Menu Contract
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ThematicMenu",
  "type": "object",
  "properties": {
    "menu_id": { "type": "string" },
    "theme_name": { "type": "string", "description": "Culinary theme (e.g. Mediterranean Harvest, Artisan Deli)" },
    "mains": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": { "type": "string" },
          "description": { "type": "string" },
          "allergens": { "type": "array", "items": { "type": "string" } },
          "dietary_labels": { "type": "array", "items": { "type": "string" } }
        },
        "required": ["name"]
      },
      "minItems": 1,
      "maxItems": 3
    },
    "sides": {
      "type": "array",
      "items": { "type": "object", "properties": { "name": { "type": "string" } }, "required": ["name"] },
      "minItems": 2,
      "maxItems": 3
    },
    "beverages": {
      "type": "array",
      "items": { "type": "object", "properties": { "name": { "type": "string" } }, "required": ["name"] },
      "minItems": 1
    },
    "desserts": {
      "type": "array",
      "items": { "type": "object", "properties": { "name": { "type": "string" } }, "required": ["name"] },
      "minItems": 1
    }
  },
  "required": ["theme_name", "mains", "sides", "beverages", "desserts"]
}
```

### 4.3 Unified Booking Record Contract
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "BookingRecord",
  "type": "object",
  "properties": {
    "booking_id": { "type": "string", "pattern": "^bk_[0-9]+_[a-f0-9]{6}$" },
    "time_slot": { "type": "string", "description": "e.g. Monday 12:00-13:00" },
    "reason": { "type": "string" },
    "booked_at": { "type": "string", "format": "date-time" },
    "catering_menu": {
      "type": "object",
      "properties": {
        "theme_name": { "type": "string" },
        "selected_items": { "type": "array", "items": { "type": "string" } }
      },
      "required": ["theme_name", "selected_items"]
    }
  },
  "required": ["booking_id", "time_slot", "booked_at"]
}
```

---

## 5. Behavior-Driven Development (BDD) Acceptance Scenarios

### Scenario 1: Propose 3 Thematic Catering Menus
```gherkin
Given the catering menu dataset contains available items across mains, sides, beverages, and desserts
When the user requests lunch planning without any conflicting dietary constraints
Then cater_agent queries the catering data via BigQuery MCP (or local fallback)
And returns exactly 3 themed menus
And each menu contains 1 to 3 main dishes, 2 to 3 side dishes, at least 1 beverage, and at least 1 dessert
And the orchestrator formats all 3 menus into the structured proposal
```

### Scenario 2: Filter Catering Menus by Active Dietary Preferences
```gherkin
Given a stored dietary preference exists stating "Alice is allergic to peanuts" and "Bob is vegetarian"
When a lunch proposal is requested
Then cater_agent retrieves all team dietary preferences from memory
And queries catering menu items excluding any item containing "peanuts" or "peanut oil"
And ensures all proposed menus include vegetarian-compliant main and side options
And the synthesized proposal explicitly notes: "Filtered to accommodate: Peanut allergy (Alice), Vegetarian (Bob)"
```

### Scenario 3: Store and Acknowledge Dietary Preference Update
```gherkin
Given the user provides input: "Dave cannot eat gluten due to celiac disease"
When the orchestrator processes the turn
Then it routes the request to cater_agent's dietary memory tool
And persists a new preference record with person_name="Dave", preference_type="allergy", details="gluten"
And returns a confirmation: "Saved dietary preference for Dave: gluten allergy. This will be applied to all future lunch recommendations."
And does NOT trigger meeting booking or time slot generation
```

### Scenario 4: Persist Selected Catering Menu in Booking
```gherkin
Given 3 proposed lunch slots and 3 catering menus were presented
When the user responds: "Book Tuesday 12:00-13:00 with Menu 1: Baja Fiesta"
Then the orchestrator delegates the booking to sched_agent
And sched_agent persists the booking record with time_slot="Tuesday 12:00-13:00" and catering_menu={"theme_name": "Baja Fiesta", "selected_items": ["Grilled Mahi Mahi Tacos", "Roasted Corn & Black Bean Salad", "Lime Crema & Tortilla Chips", "Hibiscus Agua Fresca", "Churros with Chocolate Sauce"]}
And returns a successful booking confirmation containing the booking ID and catering summary
```

### Scenario 5: Graceful Fallback in Local/Offline Mode
```gherkin
Given the agent is running locally without an active Google Cloud connection or BigQuery MCP endpoint
When cater_agent is invoked to retrieve menu options
Then cater_agent detects the MCP unavailability without crashing
And queries the local catering dataset
And successfully delivers 3 structured thematic menus adhering to all course requirements
```

---

## 6. Non-Functional Requirements (NFRs) & Security

### Security & Privacy
- **Scoping & Isolation**: Dietary preferences and booking data must be scoped cleanly per team/app namespace (`app_name="cater_agent"`, `user_id="team"` or member-specific scope).
- **Sanitization**: Free-form dietary input must be sanitized and validated against standard injection patterns before SQL generation or Memory Bank persistence.
- **Principle of Least Privilege**: When deployed to Agent Runtime, `cater_agent` uses Agent Identity Workload Federation to access BigQuery and Memory Bank without hardcoded API keys.

### Reliability & Performance
- **Timeout & Latency**: A2A catering queries must complete within 10 seconds; MCP tool calls must enforce a 5-second socket timeout.
- **Deterministic Synthesis**: The orchestrator's synthesis stage must produce structured Markdown tables and bulleted lists matching the standardized proposal schema.

---

## 7. Verification Protocol
1. **Local Agent Invocation**:
   - Start all agents locally on ports `8080` (`luncher_agent`), `8081` (`strat_agent`), `8082` (`sched_agent`), `8083` (`cater_agent`).
   - Query `http://localhost:8080/dev-ui/?app=app` with `"Plan lunch for next Tuesday"` and verify 3 menus with 1-3 mains, 2-3 sides, beverage, and dessert.
2. **Preference Memory Verification**:
   - Send prompt `"Alice is vegan"` and verify memory record creation in local store without booking.
   - Send follow-up `"Plan lunch for Wednesday"` and verify non-vegan options are filtered out from mains/sides.
3. **Booking Verification**:
   - Confirm a meeting and verify the booking payload in Memory Bank / in-memory store contains `catering_menu`.
4. **Automated Evaluation Suite**:
   - Run `agents-cli eval generate` and `agents-cli eval grade` using `tests/eval/datasets/catering-dataset.json` and `eval_config.yaml` to ensure passing scores on `final_response_quality`, `hallucination`, and `dietary_filtering`.

---

## 8. Spec Council Review Scorecard

| Reviewer | Dimension | Score (0-100) | Consensus Finding / Directives |
| :--- | :--- | :---: | :--- |
| 🧑‍💼 **Product Reviewer** | INVEST & User Alignment | Pending | Subagent review in progress |
| 🏗️ **Tech Reviewer** | Feasibility & Data Contracts | Pending | Subagent review in progress |
| 🛡️ **Security Reviewer** | OWASP, RBAC & Scoping | Pending | Subagent review in progress |
| ⚖️ **Council Chair** | Synthesis & Gating | Pending | Subagent review in progress |

