# -*- coding: utf-8 -*-
"""Pimp My PartDesign user interface language: English (default) or Turkish.

UI strings are written in English in the code and wrapped with T(); when Turkish is selected T() looks them
up in the TR table below (format placeholders such as %s / %.3f must stay the same).

The language is stored in FreeCAD's parameters:
    User parameter:BaseApp/Preferences/Mod/PimpMyPartDesign  ->  Language = "auto" | "en" | "tr"
"auto" (the default) follows FreeCAD's own language: Turkish if FreeCAD runs in Turkish, English otherwise.
"""
import FreeCAD as App

PARAM = "User parameter:BaseApp/Preferences/Mod/PimpMyPartDesign"
LANGUAGES = ("en", "tr")

_lang = None


def setting():
    return App.ParamGet(PARAM).GetString("Language", "auto")


def language():
    """Effective language code ("en" or "tr")."""
    global _lang
    if _lang is None:
        s = setting()
        if s in LANGUAGES:
            _lang = s
        else:
            gl = App.ParamGet("User parameter:BaseApp/Preferences/General").GetString("Language", "")
            _lang = "tr" if gl.lower().startswith(("turk", "tr")) else "en"
    return _lang


def set_language(lang):
    """Store the language ("auto", "en" or "tr"); the UI picks it up the next time a tool opens."""
    global _lang
    App.ParamGet(PARAM).SetString("Language", lang)
    _lang = None


def T(text):
    return TR.get(text, text) if language() == "tr" else text


TR = {
    'Dome':
        'Kubbe',
    'Edit Dome':
        'Kubbeyi düzenle',
    'Height':
        'Yükseklik',
    'Reversed (cut into the solid)':
        'Ters (katının içine oyar)',
    'PartDesign: raise a flat face into a dome that meets its edges tangent to the neighbouring faces, filleted edges and vertical walls alike':
        'PartDesign: düz bir yüzü, kenarlarda komşu yüzlere teğet bir kubbeye dönüştürür; fillet\'li kenarda da dik duvarda da',
    'Dome: select one flat face of a PartDesign Body.\n':
        "Kubbe: bir PartDesign Body'nin tek bir düz yüzünü seçin.\n",
    'Dome: the face is missing':
        'Kubbe: yüz bulunamadı',
    'Dome: the face must be flat':
        'Kubbe: yüz düz olmalı',
    'Dome: the Body has no solid yet':
        "Kubbe: Body'de henüz katı yok",
    'Dome: the face is not on the previous solid; select it again on the last feature':
        'Kubbe: yüz önceki katıda yok; son adımın üzerinde yeniden seçin',
    'Dome: the height must be above zero':
        'Kubbe: yükseklik sıfırdan büyük olmalı',
    'Dome: the surface failed (%s)':
        'Kubbe: yüzey kurulamadı (%s)',
    'Dome: the outline has parts too narrow for the surface':
        'Kubbe: dış çizgide yüzey için fazla dar bölgeler var',
    'Dome: the dome runs into another part of the solid; lower the height':
        'Kubbe: kubbe katının başka bir yerine giriyor; yüksekliği azaltın',
    'Tangent error at the edges: %.3f degrees':
        'Kenarlarda teğet hatası: %.3f derece',
    '%d edge(s) next to a steep wall are not tangent':
        '%d kenar dik duvarın yanında ve teğet değil',
    'Tangent to steep walls (bullet shape)':
        'Dik duvarlara teğet (mermi biçimi)',
    'Off: a smooth bump with a free slope at steep walls':
        'Kapalıyken: dik duvarlarda eğimi serbest, yumuşak bir tümsek',
    'Magic Loft':
        'Sihirli Loft',
    'Magic Loft Cut':
        'Sihirli Loft Oyma',
    'Edit Magic Loft':
        'Sihirli Loft düzenle',
    'PartDesign: add a clean loft through two or more closed profiles (also 3D edge loops), with selected or automatic guides. Open curves in the selection become guides':
        'PartDesign: iki ya da daha fazla kapalı profilden (3B kenar halkaları da) temiz loft ekler; rehberler seçilir ya da otomatik oluşur. Seçimdeki açık eğriler rehber olur',
    'PartDesign: cut a loft through two or more closed profiles, with selected or automatic guides':
        'PartDesign: iki ya da daha fazla kapalı profilden loft oyar; rehberler seçilir ya da otomatik oluşur',
    'Magic Loft: select at least two closed profiles (flat faces, closed edge loops or closed sketches); open curves become guides.\n':
        "Sihirli Loft: en az iki kapalı profil seçin (düz yüz, kapalı kenar halkası ya da kapalı sketch); açık eğriler rehber olur.\n",
    'Magic Loft: the profiles must belong to a PartDesign Body.\n':
        "Sihirli Loft: profiller bir PartDesign Body'ye ait olmalı.\n",
    'Magic Loft: at least two profiles are needed':
        'Sihirli Loft: en az iki profil gerekir',
    'Magic Loft: profile %d: %s':
        'Sihirli Loft: profil %d: %s',
    'Magic Loft: two profiles are on top of each other':
        'Sihirli Loft: iki profil üst üste',
    'Magic Loft: the profiles are on top of each other':
        'Sihirli Loft: profiller üst üste',
    'Magic Loft: Tangent needs a solid face next to profile %d':
        'Sihirli Loft: Yüzeye teğet için profil %d yanında bir katı yüzü gerekir',
    'Magic Loft: a guide must be an open curve (%s)':
        'Sihirli Loft: rehber açık bir eğri olmalı (%s)',
    'Magic Loft: guide %d is %.3f mm away from profile %d':
        'Sihirli Loft: rehber %d, profil %d kesitinden %.3f mm uzakta',
    'Magic Loft: the surface failed (%s)':
        'Sihirli Loft: yüzey kurulamadı (%s)',
    'Magic Loft: the surface gave an invalid solid':
        'Sihirli Loft: yüzey geçersiz bir katı verdi',
    'Magic Loft: the boolean with the Body failed':
        "Sihirli Loft: Body ile boolean başarısız",
    "Magic Loft: can't use that selection (%s)":
        'Sihirli Loft: bu seçim kullanılamıyor (%s)',
    'Magic Loft: a corner-to-round transition: PartDesign Thickness may give no wall here. Cut the inside with a Magic Loft Cut instead.\n':
        'Sihirli Loft: köşeliden yuvarlağa geçiş: PartDesign Thickness burada et vermeyebilir. İçini Sihirli Loft Oyma ile boşaltın.\n',
    'Profiles':
        'Profiller',
    'Up':
        'Yukarı',
    'Down':
        'Aşağı',
    'Add selection':
        'Seçimi ekle',
    'Remove':
        'Çıkar',
    'Start / end constraints':
        'Başlangıç / bitiş kısıtları',
    'Start':
        'Başlangıç',
    'End':
        'Bitiş',
    'Free':
        'Serbest',
    'Normal to profile':
        'Profile dik',
    'Tangent to face':
        'Yüzeye teğet',
    'Tangent strength':
        'Teğet gücü',
    'Guides':
        'Rehberler',
    'Draw ready guides':
        'Hazır rehber çiz',
    'Automatic guides you edit on screen. The selected guides are kept but not used while this is on':
        'Ekranda düzenlenen otomatik rehberler. Bu açıkken seçili rehberler saklanır ama kullanılmaz',
    'Number of guides':
        'Rehber sayısı',
    'Changing the number rebuilds the automatic guides; edits on them are lost':
        'Sayı değişince otomatik rehberler yeniden kurulur; üzerlerindeki düzenlemeler kaybolur',
    'Show preview':
        'Önizleme göster',
    'Zebra':
        'Zebra',
    'Reflection stripes on the surface, to judge its quality. Shown when you release the mouse':
        'Yüzey kalitesini görmek için yansıma çizgileri. Fare bırakılınca gösterilir',
    'Fit tolerance':
        'Oturtma toleransı',
    'Largest deviation of the surface fit: smaller is more exact, larger has fewer control points':
        'Yüzey oturtmasının en büyük sapması: küçük değer daha hassas, büyük değer daha az kontrol noktası',
    'Add point':
        'Nokta ekle',
    'Click a guide point in the 3D view and move it with the gizmo (arrows: along an axis, squares: in a plane, cube: free) or drag the point itself. The white end points belong to the profiles and stay put. Click the curve to pick a span: Add point puts the new point where you clicked.':
        '3B görünümde bir kılavuz noktasına tıklayın ve gizmo ile taşıyın (oklar: eksen boyunca, kareler: düzlemde, küp: serbest) ya da noktanın kendisini sürükleyin. Beyaz uç noktalar profillere aittir, yerinde kalır. Bir eğri parçası seçmek için eğriye tıklayın: Nokta ekle yeni noktayı tıkladığınız yere koyar.',
    'Delete point':
        'Nokta sil',
    'Edit Rail Pipe':
        'Raylı boruyu düzenle',
    'Elasticity':
        'Esneklik',
    'End scale':
        'Uç ölçeği',
    'Guide':
        'Kılavuz',
    'Move neighbors':
        'Komşular da gelsin',
    'Options':
        'Seçenekler',
    'Shell (hollow pipe, open ends)':
        'Kabuk (içi boş, uçları açık boru)',
    'Makes the pipe hollow with the wall thickness below; computed when you press OK':
        "Boruyu aşağıdaki et kalınlığıyla içi boş yapar; OK'e basınca hesaplanır",
    'Wall thickness':
        'Et kalınlığı',
    'Rail Pipe: the wall is too thick for the profile':
        'Raylı boru: et kalınlığı profil için fazla',
    'New Magic Lofts in their own Body':
        "Yeni Sihirli Loft'lar kendi Body'sinde",
    'New Rail Pipes in their own Body':
        "Yeni raylı borular kendi Body'sinde",
    "PartDesign: each new Rail Pipe gets its own Body, so pipes don't recompute and fuse together (faster). Applies to the next pipe; in the Part workbench pipes are always separate solids":
        "PartDesign: her yeni raylı boru kendi Body'sinde olur, borular birlikte yeniden hesaplanmaz ve birleştirilmez (daha hızlı). Sonraki boruya uygulanır; Part workbench'te borular her zaman ayrı katıdır",
    'Rail Pipe in its own Body':
        "Raylı boru kendi Body'sinde",
    "PartDesign: each new Rail Pipe gets its own Body (its profiles are bound with SubShapeBinders), so pipes don't recompute and fuse together. Fuse the Bodies later if you need one solid":
        "PartDesign: her yeni raylı boru kendi Body'sinde olur (profilleri SubShapeBinder ile bağlanır), borular birlikte yeniden hesaplanmaz ve birleştirilmez. Tek katı gerekirse Body'leri sonra birleştirin",
    'PartDesign: add a pipe along a guide curve from a flat face or closed sketch to a second one or a free end. Edit GuidePoints, Tension and EndScale in the property view':
        "PartDesign: düz bir yüzden ya da kapalı sketch'ten ikincisine ya da serbest uca, kılavuz eğri boyunca boru ekler. GuidePoints, Tension ve EndScale özellik panelinden düzenlenir",
    'PartDesign: cut a groove along a guide curve from a flat face or closed sketch (and to a second one). Edit GuidePoints, Tension and EndScale in the property view':
        "PartDesign: düz bir yüzden ya da kapalı sketch'ten (ve ikincisine) kılavuz eğri boyunca kanal oyar. GuidePoints, Tension ve EndScale özellik panelinden düzenlenir",
    'Rail Groove':
        'Raylı kanal',
    'Rail Pipe':
        'Raylı boru',
    'Rail Pipe: a free end needs at least one guide point':
        'Raylı boru: serbest uç için en az bir kılavuz noktası gerekir',
    'Rail Pipe: select one or two flat faces, closed edges or closed sketches of a PartDesign Body.\n':
        "Raylı boru: bir PartDesign Body'nin bir ya da iki düz yüzünü, kapalı kenarını veya kapalı sketch'ini seçin.\n",
    'Rail Pipe: the selected edges must form one closed loop':
        'Raylı boru: seçili kenarlar tek bir kapalı halka oluşturmalı',
    'Rail Pipe: the closed edges must lie in one plane':
        'Raylı boru: kapalı kenarlar tek bir düzlemde olmalı',
    'Rail Pipe: the faces must belong to a PartDesign Body.\n':
        "Raylı boru: yüzler bir PartDesign Body'ye ait olmalı.\n",
    'Rail Pipe: the first sweep failed; adjust GuidePoints in the property view.\n':
        "Raylı boru: ilk süpürme başarısız; GuidePoints'i özellik panelinden düzenleyin.\n",
    'Rail Pipe: the sketch has no closed profile':
        "Raylı boru: sketch'te kapalı profil yok",
    'Rail Pipe: the start face is missing':
        'Raylı boru: başlangıç yüzü bulunamadı',
    'Rail Pipe: the start face must be flat':
        'Raylı boru: başlangıç yüzü düz olmalı',
    'Rail Pipe: the sweep failed (%s)':
        'Raylı boru: süpürme başarısız (%s)',
    'Rail Pipe: the guide bends tighter (radius %.1f mm) than the profile (%.1f mm), the pipe folds onto itself. '
    'Move the guide points to widen the bend':
        'Raylı boru: kılavuz profilden dar kıvrılıyor (yarıçap %.1f mm, profil %.1f mm), boru kendi üstüne katlanıyor. '
        'Kıvrımı genişletmek için kılavuz noktalarını taşıyın',
    'Rail Pipe: the sweep gave an invalid solid':
        'Raylı boru: süpürme geçersiz bir katı verdi (eğri çok dar kıvrılıyor olabilir)',
    'Rail Pipe: the sweep gave no solid':
        'Raylı boru: süpürmeden katı çıkmadı',
    'Rail Pipe: two guide points are on top of each other':
        'Raylı boru: iki kılavuz noktası üst üste',
    'Reversed':
        'Ters',
    'Guide influence':
        'Rehber etkisi',
    'How far a guide acts sideways: larger gives a broader, smoother surface between guides, smaller a narrower ridge':
        'Rehberin yana ne kadar etki ettiği: büyük değer rehberler arasında daha geniş ve düzgün yüzey, küçük değer daha dar bir sırt verir',
    'Selected point':
        'Seçili nokta',
    'Ctrl+click guide points to select several: they move and delete together':
        'Birden çok rehber noktası seçmek için Ctrl+tık: birlikte taşınır ve silinir',
    'Tension':
        'Gerginlik',
    'The guide follows the dragged point like a cable':
        'Kılavuz, sürüklenen noktayı kablo gibi izler',
}
