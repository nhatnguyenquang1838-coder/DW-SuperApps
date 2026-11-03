import { redirect } from "next/navigation";

export default function Home() {
  // DWO v2: Task-first entry point.
  redirect("/tasks");
}
