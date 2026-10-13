"""
Synthetic Arabic civil-status dataset generator (practice data for the hackathon).

Creates, inside ./data :
  citizens.csv / citizens.json   - one row per person (families are internally consistent)
  events.csv                     - civil events: birth / marriage / divorce / death registrations
  offices.csv                    - civil-status offices (name, governorate, hours, phone)
  knowledge_base/*.md            - Arabic procedure documents (how to get an ID, register a birth...)
  eval_questions.json            - test questions + expected answers to measure your bot

ALL DATA IS FAKE. Fees, rules and numbers are invented for practice only.

Usage:  python generate_dataset.py --families 300 --seed 42
"""
import argparse, csv, json, os, random
from datetime import date, timedelta

MALE = ["محمد", "أحمد", "خالد", "عمر", "يوسف", "علي", "حسن", "إبراهيم", "سامي", "زيد", "طارق",
        "مالك", "فيصل", "عبدالله", "عبدالرحمن", "ليث", "معاذ", "بلال", "رامي", "وليد", "هاني",
        "نبيل", "ماجد", "سيف", "قيس", "أنس", "مراد", "باسل", "جمال", "عادل"]
FEMALE = ["فاطمة", "مريم", "سارة", "نور", "رنا", "لينا", "هبة", "ياسمين", "آمنة", "دينا", "رهف",
          "سلمى", "جنى", "ريم", "عبير", "منى", "هالة", "رغد", "تسنيم", "بيان", "لجين", "ميرا",
          "شهد", "آية", "رزان", "دانة", "سجى", "حلا", "أريج", "نسرين"]
FAMILIES = ["العواملة", "الخطيب", "النابلسي", "الزعبي", "العبادي", "الحياري", "المجالي", "الطراونة",
            "الشريف", "القضاة", "البطاينة", "العمري", "الرواشدة", "الكركي", "الحسيني", "الصمادي",
            "الخوالدة", "الفايز", "العدوان", "الدباس", "السلطي", "الحمود", "الربابعة", "الشوابكة"]
GOVS = ["عمّان", "إربد", "الزرقاء", "البلقاء", "الكرك", "معان", "الطفيلة", "مادبا", "جرش",
        "عجلون", "المفرق", "العقبة"]
OFFICES = {g: f"مكتب أحوال مدنية {g}" for g in GOVS}
OFFICES["عمّان"] = "مكتب أحوال مدنية عمّان - المركز الرئيسي"

TODAY = date(2026, 10, 13)


def rdate(start, end):
    return start + timedelta(days=random.randint(0, max(0, (end - start).days)))


class IdGen:
    """10-digit fake national numbers; first digit 9 = male, 8 = female (invented rule)."""
    def __init__(self):
        self.used = set()

    def new(self, gender):
        while True:
            n = ("9" if gender == "ذكر" else "8") + "".join(random.choices("0123456789", k=9))
            if n not in self.used:
                self.used.add(n)
                return n


def person(ids, gender, first, father, grandfather, family, mother_name, dob, gov, book_no):
    status_card = random.choices(["سارية", "منتهية", "مفقودة"], [80, 15, 5])[0]
    issue = rdate(max(dob + timedelta(days=16 * 365), date(2016, 1, 1)), TODAY) if (TODAY - dob).days > 16 * 365 else None
    expiry = issue + timedelta(days=10 * 365) if issue else None
    if status_card == "منتهية" and issue:
        expiry = rdate(date(2023, 1, 1), TODAY - timedelta(days=1))
        issue = expiry - timedelta(days=10 * 365)
        if issue < dob + timedelta(days=16 * 365):  # too young for that card: keep it valid instead
            status_card = "سارية"
            issue = rdate(dob + timedelta(days=16 * 365), TODAY)
            expiry = issue + timedelta(days=10 * 365)
    if status_card == "سارية" and expiry and expiry < TODAY:
        status_card = "منتهية"
    return {
        "national_id": ids.new(gender),
        "first_name": first, "father_name": father, "grandfather_name": grandfather, "family_name": family,
        "full_name": f"{first} {father} {grandfather} {family}",
        "mother_name": mother_name,
        "gender": gender,
        "birth_date": dob.isoformat(),
        "birth_place": gov,
        "governorate": gov,
        "nationality": "أردني" if random.random() > 0.03 else random.choice(["سوري", "مصري", "فلسطيني"]),
        "marital_status": "أعزب" if gender == "ذكر" else "عزباء",
        "spouse_id": "",
        "family_book_no": book_no,
        "father_id": "", "mother_id": "",
        "id_card_issue_date": issue.isoformat() if issue else "",
        "id_card_expiry_date": expiry.isoformat() if expiry else "",
        "id_card_status": (status_card if issue else "لا يوجد (قاصر)"),
        "is_alive": "نعم", "death_date": "",
        "registration_office": OFFICES[gov],
    }


def build(n_families):
    ids, people, events = IdGen(), [], []
    ev = lambda **k: events.append({"event_id": f"EV{len(events)+1:06d}", **k})

    for f in range(n_families):
        family = random.choice(FAMILIES)
        gov = random.choice(GOVS)
        book_no = f"FB{random.randint(100000, 999999)}"
        h_dob = rdate(date(1950, 1, 1), date(1998, 12, 31))
        w_dob = h_dob + timedelta(days=random.randint(-3 * 365, 8 * 365))
        husband = person(ids, "ذكر", random.choice(MALE), random.choice(MALE), random.choice(MALE),
                         family, random.choice(FEMALE) + " " + random.choice(FAMILIES), h_dob, gov, book_no)
        w_family = random.choice(FAMILIES)
        wife = person(ids, "أنثى", random.choice(FEMALE), random.choice(MALE), random.choice(MALE),
                      w_family, random.choice(FEMALE) + " " + random.choice(FAMILIES), w_dob, gov, book_no)
        marriage = rdate(max(h_dob, w_dob) + timedelta(days=20 * 365), max(h_dob, w_dob) + timedelta(days=32 * 365))
        marriage = min(marriage, TODAY - timedelta(days=200))
        husband.update(marital_status="متزوج", spouse_id=wife["national_id"])
        wife.update(marital_status="متزوجة", spouse_id=husband["national_id"])
        ev(event_type="زواج", national_id=husband["national_id"], related_id=wife["national_id"],
           event_date=marriage.isoformat(), governorate=gov, office=OFFICES[gov],
           details=f"تسجيل عقد زواج {husband['full_name']} و {wife['full_name']}")

        # divorce (~8%)
        divorced = random.random() < 0.08
        if divorced:
            d = rdate(marriage + timedelta(days=365), TODAY - timedelta(days=30))
            husband.update(marital_status="مطلق", spouse_id="")
            wife.update(marital_status="مطلقة", spouse_id="")
            ev(event_type="طلاق", national_id=husband["national_id"], related_id=wife["national_id"],
               event_date=d.isoformat(), governorate=gov, office=OFFICES[gov],
               details=f"تسجيل واقعة طلاق بين {husband['full_name']} و {wife['full_name']}")

        kids = []
        for _ in range(random.choices([0, 1, 2, 3, 4, 5, 6], [5, 12, 22, 25, 18, 10, 8])[0]):
            g = random.choice(["ذكر", "أنثى"])
            k_dob = rdate(marriage + timedelta(days=300), min(TODAY, marriage + timedelta(days=22 * 365)))
            k = person(ids, g, random.choice(MALE if g == "ذكر" else FEMALE), husband["first_name"],
                       husband["father_name"], family, wife["first_name"] + " " + wife["family_name"],
                       k_dob, gov, book_no)
            k.update(father_id=husband["national_id"], mother_id=wife["national_id"])
            kids.append(k)
            ev(event_type="ولادة", national_id=k["national_id"], related_id=husband["national_id"],
               event_date=k_dob.isoformat(), governorate=gov, office=OFFICES[gov],
               details=f"تسجيل ولادة {k['full_name']} في {gov}")

        # death (~older husbands)
        if (TODAY - h_dob).days > 65 * 365 and random.random() < 0.3:
            dd = rdate(date(2015, 1, 1), TODAY - timedelta(days=10))
            husband.update(is_alive="لا", death_date=dd.isoformat(), id_card_status="ملغاة (وفاة)")
            if not divorced:
                wife.update(marital_status="أرملة", spouse_id="")
            ev(event_type="وفاة", national_id=husband["national_id"], related_id="",
               event_date=dd.isoformat(), governorate=gov, office=OFFICES[gov],
               details=f"تسجيل وفاة {husband['full_name']}")

        people += [husband, wife] + kids
    return people, events


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig so Excel shows Arabic
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


# ---------------------------------------------------------------- knowledge base (procedures)
KB = {
"01_بطاقة_الأحوال_المدنية.md": """# إصدار بطاقة الأحوال المدنية (الهوية الشخصية) لأول مرة

## من يحق له التقديم
يحق لكل مواطن أتم السادسة عشرة من عمره التقدم بطلب إصدار بطاقة أحوال مدنية لأول مرة.

## الوثائق المطلوبة
- شهادة الميلاد الأصلية أو قيد مدني.
- دفتر العائلة الخاص بولي الأمر.
- صورة شخصية حديثة بخلفية بيضاء.
- حضور مقدم الطلب شخصياً لأخذ البصمات.

## الرسوم
- رسوم إصدار البطاقة لأول مرة: 2 دينار.

## مدة الإنجاز
تُسلَّم البطاقة في نفس اليوم في معظم المكاتب، وخلال 3 أيام عمل كحد أقصى.

## مدة صلاحية البطاقة
صلاحية البطاقة 10 سنوات من تاريخ الإصدار.
""",
"02_تجديد_البطاقة.md": """# تجديد بطاقة الأحوال المدنية

## متى يجب التجديد
يجب تجديد البطاقة خلال 30 يوماً من تاريخ انتهاء صلاحيتها.

## الوثائق المطلوبة
- البطاقة المنتهية.
- صورة شخصية حديثة.

## الرسوم
- رسوم التجديد: 5 دنانير.
- غرامة التأخير: دينار واحد عن كل شهر تأخير بعد انتهاء المهلة، بحد أقصى 20 ديناراً.

## إمكانية التجديد إلكترونياً
يمكن تقديم طلب التجديد عبر تطبيق "سند" ثم استلام البطاقة من أقرب مكتب أحوال مدنية.
""",
"03_بدل_فاقد_أو_تالف.md": """# إصدار بدل فاقد أو بدل تالف لبطاقة الأحوال المدنية

## بدل فاقد
- يجب إحضار إقرار بالفقدان (يُعبّأ في المكتب).
- رسوم بدل الفاقد للمرة الأولى: 10 دنانير.
- رسوم بدل الفاقد للمرة الثانية فأكثر: 20 ديناراً.

## بدل تالف
- يجب إحضار البطاقة التالفة.
- رسوم بدل التالف: 5 دنانير.

## ملاحظة
عند العثور على البطاقة المفقودة بعد إصدار البدل، يجب تسليمها لأقرب مكتب أحوال مدنية لأنها تصبح ملغاة.
""",
"04_تسجيل_الولادة.md": """# تسجيل واقعة الولادة

## المهلة القانونية
يجب تسجيل الولادة خلال 30 يوماً من تاريخ الولادة. التسجيل بعد هذه المهلة يُعتبر تسجيلاً متأخراً.

## من يحق له التبليغ
الأب، أو الأم، أو الأقارب البالغون حتى الدرجة الثانية، أو مدير المستشفى التي تمت فيها الولادة.

## الوثائق المطلوبة
- تبليغ الولادة الصادر عن المستشفى.
- دفتر العائلة.
- هويات الأب والأم.

## الرسوم
- التسجيل خلال المهلة: مجاناً.
- التسجيل المتأخر (بعد 30 يوماً وقبل سنة): غرامة 10 دنانير.
- التسجيل بعد مرور سنة: يحتاج قراراً من لجنة الولادات المتأخرة.

## شهادة الميلاد
تُصدر أول شهادة ميلاد مجاناً عند التسجيل، وكل نسخة إضافية برسوم دينارين.
""",
"05_تسجيل_الوفاة.md": """# تسجيل واقعة الوفاة

## المهلة القانونية
يجب تسجيل الوفاة خلال 30 يوماً من تاريخ حدوثها.

## الوثائق المطلوبة
- تقرير الوفاة الصادر عن المستشفى أو الطبيب الشرعي.
- بطاقة الأحوال المدنية للمتوفى.
- هوية المبلِّغ.

## الرسوم
- تسجيل الوفاة: مجاناً.
- شهادة الوفاة: دينار واحد لكل نسخة.

## ما يترتب على التسجيل
تُلغى بطاقة الأحوال المدنية للمتوفى، وتُحدَّث الحالة الاجتماعية للزوج أو الزوجة إلى أرمل أو أرملة.
""",
"06_تسجيل_الزواج_والطلاق.md": """# تسجيل واقعة الزواج والطلاق

## الزواج
- يُسجَّل عقد الزواج في دائرة الأحوال المدنية خلال 30 يوماً من توثيقه في المحكمة.
- الوثائق: نسخة عقد الزواج المصدّقة من المحكمة، وهويات الزوجين.
- بعد التسجيل يُصدر دفتر عائلة جديد للزوج إن لم يكن يملك دفتراً.
- الرسوم: مجاناً.

## الطلاق
- يُسجَّل الطلاق خلال 30 يوماً من صدور حجة الطلاق.
- الوثائق: حجة الطلاق المصدّقة، ودفتر العائلة، وهويات الطرفين.
- تُحدَّث الحالة الاجتماعية للطرفين إلى مطلق/مطلقة.
- الرسوم: مجاناً.
""",
"07_دفتر_العائلة.md": """# دفتر العائلة

## ما هو دفتر العائلة
وثيقة رسمية تضم بيانات رب الأسرة وزوجته (أو زوجاته) وأبنائه غير المتزوجين.

## إصدار دفتر عائلة لأول مرة
- يُصدر تلقائياً بعد تسجيل الزواج.
- الرسوم: 10 دنانير.

## بدل فاقد لدفتر العائلة
- إقرار فقدان.
- الرسوم: 20 ديناراً.

## إضافة مولود إلى دفتر العائلة
تتم الإضافة تلقائياً عند تسجيل الولادة دون رسوم إضافية.
""",
"08_تصحيح_البيانات.md": """# تصحيح أو تعديل البيانات في السجل المدني

## تصحيح الأخطاء المادية
الأخطاء الإملائية في الاسم أو تاريخ الميلاد الناتجة عن خطأ في الإدخال تُصحَّح في المكتب مباشرة بإحضار الوثيقة الأصلية الصحيحة. الرسوم: مجاناً.

## تغيير الاسم
- يحتاج إلى قرار من لجنة تغيير الأسماء.
- يُسمح بتغيير الاسم الأول مرة واحدة فقط.
- الرسوم: 50 ديناراً.

## تعديل تاريخ الميلاد
يحتاج قراراً قضائياً من المحكمة المختصة.
""",
"09_الشهادات_والوثائق.md": """# الشهادات والوثائق المدنية

| الوثيقة | الرسوم | مدة الإنجاز |
|---|---|---|
| شهادة ميلاد (نسخة إضافية) | 2 دينار | فوري |
| شهادة وفاة | 1 دينار | فوري |
| قيد عائلي | 2 دينار | فوري |
| قيد فردي | 1 دينار | فوري |
| شهادة عدم محكومية | ليست من اختصاص الدائرة | - |

يمكن طلب القيد العائلي والقيد الفردي إلكترونياً عبر تطبيق "سند".
""",
"10_ساعات_الدوام_والتواصل.md": """# ساعات الدوام والتواصل

- ساعات الدوام الرسمي: من الأحد إلى الخميس، من 8:00 صباحاً حتى 3:00 عصراً.
- المكتب الرئيسي في عمّان يعمل أيضاً يوم السبت من 9:00 صباحاً حتى 1:00 ظهراً.
- مكتب مطار الملكة علياء يعمل على مدار الساعة لخدمات المسافرين العاجلة فقط.
- مركز الاتصال: 06-5000000 (رقم وهمي للتدريب).
- البريد الإلكتروني: info@civil-demo.jo (عنوان وهمي للتدريب).
""",
}

EVAL = [
    {"q": "كم رسوم تجديد الهوية؟", "a": "5 دنانير، مع غرامة دينار عن كل شهر تأخير بحد أقصى 20 ديناراً", "source": "02"},
    {"q": "شو الأوراق المطلوبة لتسجيل مولود جديد؟", "a": "تبليغ الولادة من المستشفى، دفتر العائلة، هويات الأب والأم", "source": "04"},
    {"q": "ضاعت هويتي للمرة الثانية، قديش بدي أدفع؟", "a": "20 ديناراً", "source": "03"},
    {"q": "ما هي مدة صلاحية بطاقة الأحوال المدنية؟", "a": "10 سنوات", "source": "01"},
    {"q": "هل يمكنني تغيير اسمي الأول أكثر من مرة؟", "a": "لا، مرة واحدة فقط وبقرار من لجنة تغيير الأسماء", "source": "08"},
    {"q": "ما هي ساعات الدوام يوم السبت؟", "a": "المكتب الرئيسي في عمّان فقط من 9 صباحاً حتى 1 ظهراً", "source": "10"},
    {"q": "كم المهلة لتسجيل الوفاة؟", "a": "30 يوماً", "source": "05"},
    {"q": "كم سعر القيد العائلي؟", "a": "2 دينار", "source": "09"},
    {"q": "هل تصدر الدائرة شهادة عدم محكومية؟", "a": "لا، ليست من اختصاص الدائرة", "source": "09"},
    {"q": "ما هي عاصمة فرنسا؟", "a": "يجب أن يرفض البوت الإجابة لأنها خارج نطاق البيانات", "source": "none"},
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--families", type=int, default=300)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="data")
    a = ap.parse_args()
    random.seed(a.seed)
    os.makedirs(os.path.join(a.out, "knowledge_base"), exist_ok=True)

    people, events = build(a.families)
    write_csv(os.path.join(a.out, "citizens.csv"), people)
    write_csv(os.path.join(a.out, "events.csv"), events)
    write_csv(os.path.join(a.out, "offices.csv"),
              [{"office_name": v, "governorate": k, "hours": "الأحد-الخميس 8:00-15:00",
                "phone": f"0{random.randint(2, 7)}-{random.randint(1000000, 9999999)}"} for k, v in OFFICES.items()])
    with open(os.path.join(a.out, "citizens.json"), "w", encoding="utf-8") as f:
        json.dump(people, f, ensure_ascii=False, indent=1)
    for name, text in KB.items():
        with open(os.path.join(a.out, "knowledge_base", name), "w", encoding="utf-8") as f:
            f.write(text)

    # record-level eval questions generated from real rows, so you can test lookups too
    sample = random.sample([p for p in people if p["id_card_issue_date"]], 5)
    for p in sample:
        EVAL.append({"q": f"متى تنتهي هوية {p['full_name']}؟", "a": p["id_card_expiry_date"], "source": "citizens"})
    married = [p for p in people if p["spouse_id"]][:3]
    for p in married:
        sp = next(x for x in people if x["national_id"] == p["spouse_id"])
        EVAL.append({"q": f"ما اسم زوج/زوجة صاحب الرقم الوطني {p['national_id']}؟", "a": sp["full_name"], "source": "citizens"})
    with open(os.path.join(a.out, "eval_questions.json"), "w", encoding="utf-8") as f:
        json.dump(EVAL, f, ensure_ascii=False, indent=1)

    print(f"people={len(people)} events={len(events)} kb_docs={len(KB)} eval_q={len(EVAL)} -> ./{a.out}")


if __name__ == "__main__":
    main()
