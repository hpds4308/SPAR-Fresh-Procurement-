import { useAuth } from "../auth/AuthContext";
import { useSupportPhone } from "../shared/useSupportPhone";
import { useSupplierPriceDeadline } from "../shared/useOrderDeadline";

export default function SupplierGuidelines() {
  const { user } = useAuth();
  const supplierName = user?.supplier_name ?? "our supplier";
  const { number: CONTACT_NUMBER, tel: CONTACT_TEL } = useSupportPhone();
  const { english: DEADLINE_EN, sinhala: DEADLINE_SI } = useSupplierPriceDeadline();

  return (
    <div className="space-y-5">
      <div className="bg-white rounded-2xl shadow-[0_10px_30px_-12px_rgba(21,56,38,0.15)] border border-sage-100 p-6 md:p-8">
        <h2 className="font-display font-semibold text-lg text-crate-950 mb-6">Supplier Guidelines</h2>

        <section className="space-y-4 text-crate-800/90 text-[15px] leading-relaxed" lang="si">
          <p>
            Sri Lankan SPAR සමූහයේ Fresh Department සමඟ අත්වැල් බැද සිටින &quot;{supplierName}&quot; ඔබට අප
            සමූහයේ හෘදයාංගම ස්තූතිය පුද කරමු!
          </p>
          <p>
            SPAR සමූහය ශ්‍රී ලංකාව තුල ව්‍යාප්තව පවතින උසස් පාරිභෝගික සේවාවක් සහිත ආයතනයකි. එබැවින් ඔබ විසින්
            අප වෙත ලබා දෙන සේවාව ද ගුණාත්මකභාවයෙන් යුතු සේවාවක් වේ යැ&apos;යි අප බලාපොරොත්තු වෙමු.
          </p>
          <div>
            <p>අප සමූහය හා අත්වැල් බැඳ සිටින ඔබ,</p>
            <ul className="list-disc pl-6 mt-1.5 space-y-1">
              <li>ඉහල ප්‍රමිතියකින් ඇති එළවලු සහ පලතුරු ලබා දීමට කටයුතු කරන්න.</li>
              <li>ඔබගේ මිළ ගණන් {DEADLINE_SI} ට පෙර අප වෙත ඉදිරිපත් කරන්න.</li>
              <li>{DEADLINE_SI}න් පසුව ඔබට මෙම පද්ධතිය හරහා මිළ ගණන් ඉදිරිපත් කල නොහැක.</li>
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

          <ul className="list-disc pl-6 space-y-4 pt-2">
            <li>
              <p className="font-semibold text-crate-950">එළවළු හෝ පලතුරු සඳහා මිල ගනන් ඉදිරිපත් කිරීම:-</p>
              <p className="mt-1.5">
                මෙහිදී submit price tab එක භාවිතා කර ඔබට මිල ගණන් ඉදිරිපත් කල හැක.
                <br />
                පලමු වර ඔබ මිල ගණන් ඉදිරිපත් කල පසු, එය මෙම පද්ධතිය මඟින් ගබඩා කර තබා ගනී.
                <br />
                ඔබ විසින් නැවත මිළ ගණන් ඉදිරිපත් කිරීමේ දී පරණ මිල ගණන් submit price යටතේ පෙන්වයි.
                <br />
                වෙබ් පිටුවේ අවසාන කොටසේ clear all මත click කිරීමෙන් පරණ මිල ගණන් ඉවත් කරගත් පසුව නව මිල ගණන් ඔබට
                ඇතුලත් කල හැක.
                <br />
                පෙර දිනයේ මිල ගණන් නැවත වෙනස් නොවන්නේනම් එය clear all නොකර submit කල හැක.
                <br />
                නැතිනම් නව clear all කර නව මිළ ගණන් ඉදිරිපත් කර submit කල හැක.
              </p>
              <p className="mt-3">
                ඔබ excel file එකක් භාවිතා කර මිල ගණන් ඉදිරිපත් කරන්නේ නම්, submit price tab යටතේ ඇති තිරයේ
                Download Excel Sheet මඟින් excel file format එකක් download කර ගත හැක.
                <br />
                පසුව එම excel file එක වෙත මිළ ගණන් ඇතුලත් කර submit prices tab යටතේ upload excel option එක හරහා
                එය submit කල හැක.
              </p>
              <p className="mt-3">
                මිළ ගණන් සාර්ථකව ඉදිරිපත් වූ පසු Prices Submitted Successfully යනුවෙන් දිස්වේ.
                <br />
                එසේ නොවේනම් ඉහත ඇති දුරකතනය අමතන්න.
              </p>
            </li>
            <li>
              ඉදිරිපත් කෙරූ මිල ගණන් My Submitted Prices tab යටතේ ද,
              <br />
              ඉදිරිපත් කල නව මිළ ගණන් වෙනස් වීම Price Approvals යටතේ ද,
              <br />
              ඉදිරිපත් කල මිල ගණන් වෙනස් වූ පසු අවසාන මිල Final Price Tab යටතේ ද,
              <br />
              ශාඛා සඳහා ඇණවුම් Orders by Branch Tab යටතේ ද,
              <br />
              මිල ගණන් ඇතුලත් ඇණවුම් Purchase Orders යටතේ ද,
              <br />
              SPAR Head Office සඳහා පණිවිඩ එක් කිරීම Messages යටතේ ද,
              <br />
              සැපයුම්කරුගේ මාර්ගෝපදේශ Supplier Guidelines Tab යටතේ ද,
              <br />
              ඔබගේ ගිණුමේ තොරතුරු ඇතුලත් කිරීම Account Tab යටතේ ද ලබා ගත හැක.
            </li>
          </ul>
        </section>

        <div className="border-t border-sage-100 my-7" />

        <section className="space-y-4 text-crate-800/90 text-[15px] leading-relaxed" lang="en">
          <p>
            We extend our heartfelt thanks to &ldquo;{supplierName}&rdquo; for partnering with the Fresh
            Department of the Sri Lankan SPAR Group!
          </p>
          <p>
            SPAR Group is an organization with a strong presence throughout Sri Lanka, providing a high
            standard of customer service. Therefore, we expect the services you provide to us to be of the
            same high quality.
          </p>
          <p>
            As a valued partner of our group, please ensure that you provide high-quality vegetables and
            fruits that meet the required standards.
          </p>
          <p>
            Please submit your prices to us before {DEADLINE_EN}. After {DEADLINE_EN}, you will not be able to
            submit your prices through this system.
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
