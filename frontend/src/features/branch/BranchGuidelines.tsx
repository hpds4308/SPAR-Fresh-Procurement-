import { useAuth } from "../auth/AuthContext";
import { useSupportPhone } from "../shared/useSupportPhone";
import { useOrderDeadline } from "../shared/useOrderDeadline";

export default function BranchGuidelines() {
  const { user } = useAuth();
  const branchName = user?.branch_name ?? "our branch";
  const { number: CONTACT_NUMBER, tel: CONTACT_TEL } = useSupportPhone();
  const { english: DEADLINE_EN, sinhala: DEADLINE_SI } = useOrderDeadline();

  return (
    <div className="space-y-5">
      <div className="bg-white rounded-2xl shadow-[0_10px_30px_-12px_rgba(21,56,38,0.15)] border border-sage-100 p-6 md:p-8">
        <h2 className="font-display font-semibold text-lg text-crate-950 mb-6">Branch Guidelines</h2>

        <section className="space-y-4 text-crate-800/90 text-[15px] leading-relaxed" lang="si">
          <p>
            Sri Lankan SPAR සමූහයේ Fresh Department සමඟ සම්භන්ධ වූ ඔබ {branchName}, ශාඛාවයි.
          </p>
          <p>
            SPAR සමූහය ශ්‍රී ලංකාව තුල ව්‍යාප්තව පවතින උසස් පාරිභෝගික සේවාවක් සහිත ආයතනයකි. එබැවින් ඔබ විසින්
            සපයන සේවාව ද ගුණාත්මකභාවයෙන් යුතු සේවාවක් වේ යැ&apos;යි අප බලාපොරොත්තු වෙමු.
          </p>
          <div>
            <p>අප සමූහයේ {branchName} ඔබ,</p>
            <ul className="list-disc pl-6 mt-1.5 space-y-1">
              <li>ඔබගේ ඇනවුම් {DEADLINE_SI} ට පෙර අප වෙත ඉදිරිපත් කරන්න.</li>
              <li>{DEADLINE_SI}න් පසුව ඔබට මෙම පද්ධතිය හරහා ඇනවුම් ඉදිරිපත් කල නොහැක.</li>
              <li>{DEADLINE_SI}න් පසු ඔබ කිසිවක් ඇනවුම් කර නැත්නම් සතියකට පෙර ඔබගේ ඇනවුම මෙම පද්ධතිය මඟින් ලබා ගනී.</li>
            </ul>
          </div>
          <p>
            ඔබට කිසියම් ගැටලුවක් හෝ අවශ්‍යතාවයක් ඇත්නම්{" "}
            <a href={`tel:${CONTACT_TEL}`} className="text-crate-700 font-semibold hover:underline">
              {CONTACT_NUMBER}
            </a>{" "}
            අමතන්න.
          </p>
          <p className="font-semibold text-crate-950">ස්තූතියි!</p>
        </section>

        <div className="border-t border-sage-100 my-7" />

        <section className="space-y-4 text-crate-800/90 text-[15px] leading-relaxed" lang="en">
          <p>
            You are a valued partner of the Fresh Department of the Sri Lankan SPAR Group, and you are the
            representative of the &ldquo;{branchName}&rdquo; branch.
          </p>
          <p>
            SPAR Group is an organization with a strong presence throughout Sri Lanka, providing a high
            standard of customer service. Therefore, we expect the services you provide to us to be of the
            same high quality.
          </p>
          <p>
            As a valued member of our &ldquo;{branchName}&rdquo; branch, please submit your orders to us
            before {DEADLINE_EN}.
          </p>
          <p>After {DEADLINE_EN}, you will not be able to submit orders through this system.</p>
          <p>
            If you have not placed any orders by {DEADLINE_EN}, your order from one week prior will be
            automatically obtained through this system.
          </p>
          <p>
            If you have any issues or requirements, please contact{" "}
            <a href={`tel:${CONTACT_TEL}`} className="text-crate-700 font-semibold hover:underline">
              {CONTACT_NUMBER}
            </a>
            .
          </p>
          <p className="font-semibold text-crate-950">Thank you!</p>
        </section>
      </div>
    </div>
  );
}
