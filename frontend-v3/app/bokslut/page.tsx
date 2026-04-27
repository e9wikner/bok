import { redirect } from "next/navigation";

export default function BokslutPage() {
  // Redirect to INK2 as the default bokslut page
  redirect("/bokslut/ink2");
}
