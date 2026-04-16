{
  "component": "LlmGeneratedComponent",
  "props": {
    "height": "700px",
    "prompt": "Create an optimized, comfortable dark-themed UI for a financial portfolio dashboard based on the input images. The primary objective is to resolve cut-off text and icons while significantly improving overall comfort and readability through refined spacing and a more balanced color palette. The layout should be single-column for desktop, with elements reflowing logically.

### Design Principles:

1.  **Resolve Cut-Offs:** Increase vertical padding and element spacing throughout. Text and icons must be fully visible.
2.  **Balanced Color Palette:** Use a unified dark theme with greater depth and clearly defined accent colors for each metric to create a sense of hierarchy and focus.
3.  **Refined Typography:** Use a high-readability font with appropriate weight and size, with clear separation between labels and values.
4.  **Generous Spacing:** Add breathability between cards, table rows, and individual data points.

### Components and Layout (Ordered Vertically):

**1. Page Title:**
* \"當前資產明細與交易部位概覽\" - Use a slightly smaller, more elegant icon and larger font, with better vertical padding than `image_2.png`.

**2. Key Metric Cards (Single-row, horizontally flowing):**
* **Card Background:** `#2D2D2D` (slightly lighter deep gray) with a soft shadow and subtle border.
* **Vertical Padding:** Increase card top padding to `20px` to resolve cut-offs (e.g., in `image_1.png`).
* **Common Text Color (Labels):** `#B0B0B0` (light gray).
* **Common Text Color (Values):** Use defined high-contrast highlight colors.
* **Layout per Card:** Top icon and title (e.g., [cute globe] \"USD/TWD 匯率\") in `#B0B0B0`, middle large main number (e.g., `31.954`) in highlight color, bottom secondary text (e.g., \"本金: $150,000\" in `#B0B0B0`, where applicable). Add more breathing room between these three elements.

* **Card 1: USD/TWD 匯率**
    * Highlight Color: `#64B5F6` (light blue)
* **Card 2: 資產總市值**
    * Highlight Color: `#4DD0E1` (light cyan)
* **Card 3: 今日損益跳動**
    * Highlight Color: `#E57373` (light red)
* **Card 4: 真實總累積損益**
    * Highlight Color: `#81C784` (light green)
    * Include the本金 secondary text at the bottom.

**3. Financial Freedom Milestone Progress (`image_12.png` area):**
* **Section Title:** \"🏆 財務自由闖關進度\"
* **Layout:** Group each milestone (`LV`) with its icon, percentage label, and value, providing clear breathing room.
    * Icon & Label: \"LV 啟航\" (Top)
    * Percentage: `750萬` (Middle)
    * Value (Secondary): \"（已達成）\" (cite: use `#81C784` green text here for consistency with success) or just leave it.
* **Progress Bar:** Use the cyan (`#4DD0E1`) color for the current progress and `#444444` for the remaining distance. Show the \"目前總市值\" text on top. Add better spacing below this entire section.

**4. Table: 當前資產部位與交易明細 (`image_2.png` / `image_3.png` area):**
* **Table Container:** Use 交替行背景色（`#2A2A2A` and `#323232`）to improve row definition.
* **Vertical Spacing:** Increase table row height and vertical padding (`padding: 12px 10px`).
* **Headers:** High-contrast text with better internal spacing (e.g., ensure `成本` and `市值` don't collide).
* **Column Alignment:** Ensure values within columns are perfectly aligned with headers.
* **Highlight Color Consistency:** For transaction advice (like `減碼 783 股` in `image_5.png`), use the light cyan (`#4DD0E1`) key metric color instead of green to differentiate from the profit/loss green metric.
* **Typography:** Use `#FFFFFF` or `#E0E0E0` for main numbers in the table. Use `#B0B0B0` for descriptive labels like the number of shares and units in the input fields of `image_4.png` area.

### Final Touches for Comfort:

* Overall app background: `#242424` (dark gray).
* Add light-gray descriptive text (`#B0B0B0`) below complex interactive areas to guide the user.
* Ensure a consistent color language:
    * **Success/Profit:** Green (`#81C784`).
    * **Loss/Warning:** Red (`#E57373`).
    * **Transaction Advice (Neutral):** Cyan (`#4DD0E1`).
    * **Main Metric Colors:** As defined above (cite: Blue, Cyan, Red, Green)."
  }
}
