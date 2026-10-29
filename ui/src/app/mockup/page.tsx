import Link from "next/link";
import { MockupDemo } from "./mockup";

export const metadata = { title: "InstallGate · design mockup" };

export default function Mockup() {
  return (
    <>
      <p className="m-0 border-b border-[#DDE1E7] px-4 py-2 text-[13px] text-[#4B5563] md:px-6">
        Design mockup with sample data. Nothing here is a live verdict.{" "}
        <Link href="/" className="font-medium text-[#14171C] underline">
          Open the live gate
        </Link>
      </p>
      <MockupDemo />
    </>
  );
}
