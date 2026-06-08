# Sim Delivery System Product Skeleton Design

**Scope**

This design covers the next implementation wave for the internal project management system:

1. Clean the dashboard homepage by removing prototype-only placeholder content.
2. Build a dedicated project creation page.
3. Build a dedicated project list page.
4. Build a dedicated project detail page.

The work follows a page-by-page approach instead of packing all functions into one screen.

**Goals**

- Turn the current demo-like dashboard into a usable business homepage.
- Keep the visual style modern and clean, but remove meaningless placeholder copy.
- Establish a stable multi-page product skeleton that can support later backend integration.
- Preserve the current internal-use workflow: fixed project stages, manual progress updates, project amount tracking, configurable project directories, and delivery packaging.

**Non-Goals**

- No customer portal in this phase.
- No complex approval workflow in this phase.
- No multi-role permission system in this phase.
- No automatic file-scanning completion logic in this phase.

**Information Architecture**

The product is split into four primary pages:

1. Dashboard
2. New Project
3. Project List
4. Project Detail

The sidebar remains the main navigation entry and should point to these real pages instead of acting as decorative tabs.

**Homepage Design**

The homepage should answer three management questions immediately:

1. How many projects are active right now?
2. Which projects are close to delivery or blocked?
3. Where are the amounts and project stages concentrated?

The homepage keeps these modules:

- Header with business-oriented title and short description.
- Backend connection status indicator.
- Four KPI cards:
  - Project count
  - Total project amount
  - Near-delivery projects
  - Ready-to-package projects
- Three charts:
  - Stage distribution
  - Monthly delivery trend
  - Top projects by amount
- One risk reminder panel focused on actionable items.

The homepage removes these prototype-only elements:

- Generic version names such as "Dashboard V2"
- Decorative explanatory copy with no operational value
- Fake product-marketing descriptions
- Embedded project detail panel
- Duplicate overview tables that overlap with the project list page

**New Project Page**

The new project page is the first real data-entry page and should include:

- Project name
- Customer name
- Project amount
- Planned delivery date
- Project template
- Root directory path
- Short project description

The interaction goal is simple: let the user create a project record with the minimum required business fields. The page does not yet need file-system creation or backend persistence in this phase if those are not ready.

**Project List Page**

The project list page is the operational workbench for scanning all projects. It should include:

- Search by project name or customer
- Filters for stage and status
- Key columns:
  - Project name
  - Customer
  - Current stage
  - Progress
  - Project amount
  - Planned delivery date
  - Packaging status

The list page should be concise and readable instead of trying to show all details inline.

**Project Detail Page**

The project detail page is the single-project command center. It should include:

- Basic information
- Stage progress
- Project directory path
- Delivery checklist
- Packaging records

This page replaces the current homepage-side detail concept. Detailed project operations belong here, not on the dashboard.

**Data Shape for This Phase**

Frontend mock data and backend sample APIs should align around these core fields:

- id
- name
- customer
- amount
- currentStage
- progress
- plannedDeliveryDate
- status
- packageStatus
- rootDirectory

These fields are enough to support the first real navigation structure and page rendering.

**Backend Expectations**

The current backend can stay minimal during this phase. It only needs to support the existing dashboard sample data and can later be extended for:

- project list data
- project detail data
- project creation submission

The page structure should be designed so that static mock data can be replaced by API responses without rewriting the whole UI.

**Error Handling**

- If backend data is unavailable, the UI shows a clear "sample data" state instead of broken content.
- If a page has no records, it shows an empty state with business wording, not placeholder lorem-style copy.
- If a field is not yet implemented, hide it instead of displaying meaningless filler text.

**Implementation Order**

1. Clean the homepage and remove meaningless placeholders.
2. Introduce real multi-page navigation structure.
3. Build the new project page.
4. Build the project list page.
5. Build the project detail page.
6. Expand backend sample APIs only as needed to support those pages.

**Acceptance Criteria**

- The homepage no longer contains prototype-like placeholder wording.
- The homepage focuses on KPI cards, charts, and risk reminders only.
- Project creation, project list, and project detail are separate pages.
- Navigation reflects actual pages instead of decorative placeholders.
- The UI remains visually clean and modern while becoming more business-oriented.
