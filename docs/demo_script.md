# Reflex 2-Minute Live Demo Script

**Target Time:** 120 Seconds | **Demo Manager:** Member 3 (Frontend)

---

### Step 1: Retailer Order Creation (0:00 – 0:35)
* **Screen:** Retailer Order Form
* **Action:** Member 3 inputs Customer Name, Phone Number, Address, and Item Description, then clicks **Submit Request**[cite: 1, 2].
* **Takeaway:** Delivery request logged with `LOGGED` status and unique payload tracking code[cite: 1, 2].

### Step 2: Dispatcher Assignment (0:35 – 1:10)
* **Screen:** Dispatcher Queue Board
* **Action:** Member 3 opens Dispatcher View, locates unassigned request, selects rider from dropdown, and clicks **Assign**[cite: 1, 2].
* **Takeaway:** State transitions from `LOGGED` to `ASSIGNED` in real time[cite: 1, 2].

### Step 3: Rider Execution & Scanning (1:10 – 1:45)
* **Screen:** Rider Mobile View
* **Action:** Member 3 opens assigned rider task, inputs/scans confirmation code, and updates status to `DELIVERED`[cite: 1, 2].
* **Takeaway:** Scanned payload verifies package delivery and updates global order state[cite: 1, 2].

### Step 4: System Wrap-Up & Handoff (1:45 – 2:00)
* **Screen:** Retailer Dashboard
* **Action:** Member 3 displays updated `DELIVERED` status on Retailer portal and hands off control to Member 5 for Slide 5[cite: 1, 2].
