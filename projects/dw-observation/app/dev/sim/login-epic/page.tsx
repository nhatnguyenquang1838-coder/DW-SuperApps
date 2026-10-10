import LoginEpicRunGraph from "@/components/login-epic/LoginEpicRunGraph";
import { loadLoginEpicFixture } from "@/lib/loginEpicFixture";

export default function Page() {
  const epic = loadLoginEpicFixture();
  return <LoginEpicRunGraph epic={epic} />;
}
