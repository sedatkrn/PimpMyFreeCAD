# -*- coding: utf-8 -*-
"""PartDesign Add-ins user interface language: English (default) or Turkish.

UI strings are written in English in the code and wrapped with T(); when Turkish is selected T() looks them
up in the TR table below (format placeholders such as %s / %.3f must stay the same).

The language is stored in FreeCAD's parameters:
    User parameter:BaseApp/Preferences/Mod/PartDesignAddins  ->  Language = "auto" | "en" | "tr"
"auto" (the default) follows FreeCAD's own language: Turkish if FreeCAD runs in Turkish, English otherwise.
"""
import FreeCAD as App

PARAM = "User parameter:BaseApp/Preferences/Mod/PartDesignAddins"
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
    'Rail Pipe: select one or two flat faces or closed sketches of a PartDesign Body.\n':
        "Raylı boru: bir PartDesign Body'nin bir ya da iki düz yüzünü veya kapalı sketch'ini seçin.\n",
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
    'Rail Pipe: the sweep gave an invalid solid':
        'Raylı boru: süpürme geçersiz bir katı verdi (eğri çok dar kıvrılıyor olabilir)',
    'Rail Pipe: the sweep gave no solid':
        'Raylı boru: süpürmeden katı çıkmadı',
    'Rail Pipe: two guide points are on top of each other':
        'Raylı boru: iki kılavuz noktası üst üste',
    'Reversed':
        'Ters',
    'Selected point':
        'Seçili nokta',
    'Tension':
        'Gerginlik',
    'The guide follows the dragged point like a cable':
        'Kılavuz, sürüklenen noktayı kablo gibi izler',
}
