import type { IconName } from "./ui";

// The "More" menu: every screen of the website that is not already a tab, grouped the way the website's sidebar groups them.
// `needs` hides an entry when the site has that feature switched off (the flags come from /me).
export type NavItem = { label: string; to: string; icon: IconName; needs?: "prep_enabled" | "assistant_enabled" };
export type NavGroup = { title: string; items: NavItem[] };

export const NAV: NavGroup[] = [
  {
    title: "Job search",
    items: [
      { label: "Add a job", to: "/jobs/add", icon: "add-circle-outline" },
      { label: "Saved searches", to: "/saved-searches", icon: "bookmark-outline" },
      { label: "Job sources", to: "/sources", icon: "radio-outline" },
      { label: "Prep plans", to: "/prep", icon: "school-outline", needs: "prep_enabled" },
    ],
  },
  {
    title: "After you apply",
    items: [
      { label: "Interviews", to: "/interviews", icon: "calendar-outline" },
      { label: "Contacts", to: "/contacts", icon: "people-outline" },
      { label: "Companies", to: "/companies", icon: "business-outline" },
      { label: "Question bank", to: "/questions", icon: "chatbubbles-outline" },
      { label: "Offers", to: "/offers", icon: "cash-outline" },
      { label: "Insights", to: "/insights", icon: "bar-chart-outline" },
    ],
  },
  {
    title: "About you",
    items: [
      { label: "Documents", to: "/documents", icon: "folder-outline" },
      { label: "Profile", to: "/profile", icon: "person-outline" },
      { label: "AI settings", to: "/profile/ai", icon: "sparkles-outline" },
      { label: "Connections", to: "/profile/connections", icon: "link-outline" },
      { label: "Assistant", to: "/profile/assistant", icon: "hardware-chip-outline", needs: "assistant_enabled" },
      { label: "Notifications", to: "/notifications", icon: "notifications-outline" },
      { label: "Your data", to: "/profile/data", icon: "download-outline" },
      { label: "Help", to: "/help", icon: "help-circle-outline" },
    ],
  },
];
