import LoginForm from "@/components/login-form";
import { hasValidSession } from "@/lib/auth";
import { redirect } from "next/navigation";
export const dynamic = "force-dynamic";
export default async function LoginPage() {
    if (await hasValidSession())
        redirect("/");
    return <LoginForm />;
}
