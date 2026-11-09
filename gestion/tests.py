from datetime import timedelta
from decimal import Decimal

import pyotp
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from gestion import twofa
from academie.models import Achat, Activite, Categorie, Cours, Professeur, ProfilEleve, SuiviCours

GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,"
    b"\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)
ADMIN = {"HTTP_HOST": "admin.localhost"}


def rv(nom, **kw):
    return reverse(nom, urlconf="sophos.urls_gestion", **kw)

MDP = "mot-de-passe-test-123"


@override_settings(MEDIA_ROOT="/tmp/sophos-tests-media", ADMIN_HOST="admin.localhost", ADMIN_2FA_REQUISE=True)
class BaseGestion(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user("equipe", "e@x.fr", MDP, is_staff=True)
        cls.eleve = User.objects.create_user("eleve", "el@x.fr", MDP)
        cat = Categorie.objects.create(nom="Dessin", slug="dessin")
        cls.prof = Professeur.objects.create(nom="Awa")
        cls.cours = Cours.objects.create(
            categorie=cat, titre="Aquarelle", slug="aquarelle", duree="2 h", auteur="Awa", professeur=cls.prof,
            prix=Decimal("10"), image=SimpleUploadedFile("a.gif", GIF, content_type="image/gif"),
        )

    def setUp(self):
        cache.clear()

    def get(self, nom, *args, **extra):
        return self.client.get(rv(nom, args=args), **ADMIN, **extra)

    def post(self, nom, data=None, args=(), **extra):
        return self.client.post(rv(nom, args=args), data or {}, **ADMIN, **extra)

    def connecter(self):
        self.client.force_login(self.staff)
        session = self.client.session
        session["gestion_2fa"] = self.staff.pk  # code du téléphone déjà vérifié
        session.save()


class IsolementTests(BaseGestion):
    def test_admin_inexistant_sur_le_site_public(self):
        for chemin in ["/gestion/", "/connexion-admin/", "/django-admin/", "/admin/", "/api/stats/", "/cours/nouveau/"]:
            self.assertEqual(self.client.get(chemin).status_code, 404, chemin)

    def test_site_public_inexistant_sur_le_sous_domaine_admin(self):
        self.assertEqual(self.client.get("/projets/", **ADMIN).status_code, 404)
        self.assertEqual(self.client.get("/plus/", **ADMIN).status_code, 404)

    def test_visiteur_redirige_vers_la_connexion(self):
        for nom in ["gestion:tableau_de_bord", "gestion:cours_liste", "gestion:etudiants_liste",
                    "gestion:professeurs_liste", "gestion:ventes_liste", "gestion:api_stats"]:
            r = self.get(nom)
            self.assertEqual(r.status_code, 302, nom)
            self.assertIn(rv("gestion:connexion"), r["Location"])

    def test_un_etudiant_connecte_n_entre_pas(self):
        self.client.force_login(self.eleve)
        self.assertEqual(self.get("gestion:tableau_de_bord").status_code, 403)
        self.assertEqual(self.get("gestion:api_stats").status_code, 403)

    def test_en_tetes_de_securite(self):
        r = self.get("gestion:connexion")
        self.assertIn("script-src 'self'", r["Content-Security-Policy"])
        self.assertNotIn("unsafe-inline", r["Content-Security-Policy"])
        self.assertEqual(r["X-Frame-Options"], "DENY")
        self.assertIn("no-store", r["Cache-Control"])


class ConnexionTests(BaseGestion):
    def test_mot_de_passe_seul_ne_connecte_pas(self):
        r = self.post("gestion:connexion", {"username": "equipe", "password": MDP})
        self.assertRedirects(r, rv("gestion:activation"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(self.get("gestion:tableau_de_bord").status_code, 302)

    def test_un_etudiant_ne_peut_pas_se_connecter_a_l_admin(self):
        r = self.post("gestion:connexion", {"username": "eleve", "password": MDP})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Identifiant ou mot de passe incorrect.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_meme_message_compte_inconnu_ou_mauvais_mot_de_passe(self):
        a = self.post("gestion:connexion", {"username": "equipe", "password": "faux"})
        b = self.post("gestion:connexion", {"username": "inconnu", "password": "faux"})
        self.assertContains(a, "Identifiant ou mot de passe incorrect.")
        self.assertContains(b, "Identifiant ou mot de passe incorrect.")

    def test_blocage_apres_cinq_echecs_meme_avec_le_bon_mot_de_passe(self):
        for _ in range(5):
            self.post("gestion:connexion", {"username": "equipe", "password": "faux"})
        r = self.post("gestion:connexion", {"username": "equipe", "password": MDP})
        self.assertContains(r, "Trop de tentatives")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_redirection_externe_refusee(self):
        self.post("gestion:connexion", {"username": "equipe", "password": MDP, "next": "https://pirate.example/"})
        secret = self._activer()
        self.assertEqual(self.client.session.get("gestion_2fa"), self.staff.pk)
        self.assertEqual(secret and 1, 1)

    def test_deconnexion_exige_post(self):
        self.connecter()
        self.assertEqual(self.get("gestion:deconnexion").status_code, 405)
        self.assertEqual(self.post("gestion:deconnexion").status_code, 302)

    def test_csrf_actif(self):
        from django.test import Client
        c = Client(enforce_csrf_checks=True)
        c.force_login(self.staff)
        session = c.session
        session["gestion_2fa"] = self.staff.pk
        session.save()
        r = c.post(rv("gestion:cours_publier", args=[self.cours.pk]), **ADMIN)
        self.assertEqual(r.status_code, 403)


    def _activer(self):
        """Termine l'activation du téléphone ; renvoie le secret."""
        r = self.get("gestion:activation")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.get("gestion:activation_qr")["Content-Type"], "image/svg+xml")
        appareil = twofa.appareil_de(self.staff)
        secret = twofa.dechiffrer(appareil.secret_chiffre)
        code = pyotp.TOTP(secret).now()
        r = self.post("gestion:activation", {"code": code})
        self.assertRedirects(r, rv("gestion:codes_secours"), fetch_redirect_response=False)
        return secret


class DoubleAuthTests(BaseGestion):
    def _connexion_mdp(self):
        return self.post("gestion:connexion", {"username": "equipe", "password": MDP})

    def _equiper(self):
        """Compte avec téléphone déjà activé ; renvoie (secret, codes de secours)."""
        appareil = twofa.preparer_appareil(self.staff)
        appareil.confirme = True
        appareil.save()
        return twofa.dechiffrer(appareil.secret_chiffre), twofa.generer_codes_secours(appareil)

    def test_activation_puis_codes_de_secours_affiches_une_fois(self):
        self._connexion_mdp()
        ConnexionTests._activer(self)
        r = self.get("gestion:codes_secours")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.context["codes"]), 8)
        self.assertEqual(self.get("gestion:codes_secours").status_code, 302)  # plus jamais affichés
        appareil = twofa.appareil_de(self.staff)
        self.assertTrue(appareil.confirme)
        self.assertNotIn(twofa.dechiffrer(appareil.secret_chiffre), appareil.secret_chiffre)  # chiffré en base

    def test_connexion_avec_code_puis_rejeu_refuse(self):
        secret, _ = self._equiper()
        self.assertRedirects(self._connexion_mdp(), rv("gestion:verification"), fetch_redirect_response=False)
        code = pyotp.TOTP(secret).now()
        r = self.post("gestion:verification", {"code": code})
        self.assertRedirects(r, rv("gestion:tableau_de_bord"), fetch_redirect_response=False)
        self.assertEqual(self.get("gestion:tableau_de_bord").status_code, 200)
        self.client.logout()
        self._connexion_mdp()
        r = self.post("gestion:verification", {"code": code})  # même code réutilisé
        self.assertContains(r, "Code incorrect")

    def test_mauvais_code(self):
        self._equiper()
        self._connexion_mdp()
        r = self.post("gestion:verification", {"code": "000000"})
        self.assertContains(r, "Code incorrect")
        self.assertEqual(self.get("gestion:tableau_de_bord").status_code, 302)

    def test_verification_sans_etape_mot_de_passe(self):
        self._equiper()
        r = self.post("gestion:verification", {"code": "123456"})
        self.assertRedirects(r, rv("gestion:connexion"), fetch_redirect_response=False)

    def test_code_de_secours_utilisable_une_seule_fois(self):
        _, codes = self._equiper()
        self._connexion_mdp()
        r = self.post("gestion:verification", {"code": codes[0]})
        self.assertRedirects(r, rv("gestion:tableau_de_bord"), fetch_redirect_response=False)
        self.client.logout()
        self._connexion_mdp()
        self.assertContains(self.post("gestion:verification", {"code": codes[0]}), "Code incorrect")

    def test_blocage_apres_cinq_mauvais_codes(self):
        secret, _ = self._equiper()
        self._connexion_mdp()
        for _ in range(5):
            self.post("gestion:verification", {"code": "000000"})
        r = self.post("gestion:verification", {"code": pyotp.TOTP(secret).now()})
        self.assertContains(r, "Trop de tentatives")

    def test_session_sans_verification_du_code_est_refusee(self):
        """Un compte connecté ailleurs avec le seul mot de passe (ex. site public) n'ouvre pas l'admin."""
        self._equiper()
        self.client.force_login(self.staff)
        r = self.get("gestion:tableau_de_bord")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/connexion/", r["Location"])

    def test_ancienne_admin_django_aussi_protegee(self):
        self.client.force_login(self.staff)
        r = self.client.get("/django-admin/", follow=True, **ADMIN)
        self.assertTrue(r.redirect_chain[-1][0].startswith("/connexion/"), r.redirect_chain)

    def test_attente_expiree(self):
        self._equiper()
        self._connexion_mdp()
        session = self.client.session
        session["gestion_attente"]["t"] -= 6 * 60
        session.save()
        r = self.get("gestion:verification")
        self.assertRedirects(r, rv("gestion:connexion"), fetch_redirect_response=False)


class InjectionTests(BaseGestion):
    def setUp(self):
        super().setUp()
        self.connecter()

    def test_injection_sql_dans_la_recherche_est_inoffensive(self):
        for nom in ["gestion:cours_liste", "gestion:etudiants_liste", "gestion:professeurs_liste"]:
            r = self.client.get(rv(nom), {"q": "' OR 1=1; DROP TABLE academie_cours; --"}, **ADMIN)
            self.assertEqual(r.status_code, 200, nom)
        self.assertTrue(Cours.objects.filter(pk=self.cours.pk).exists())
        r = self.client.get(rv("gestion:cours_liste"), {"q": "' OR '1'='1"}, **ADMIN)
        self.assertNotContains(r, "Aquarelle")  # la recherche est traitée comme du texte, pas comme du SQL

    def test_xss_est_echappe_a_l_affichage(self):
        Professeur.objects.create(nom="<script>alert(1)</script>")
        r = self.get("gestion:professeurs_liste")
        self.assertNotContains(r, "<script>alert(1)</script>")
        self.assertContains(r, "&lt;script&gt;alert(1)&lt;/script&gt;")

    def test_parametres_de_stats_hors_liste_blanche(self):
        r = self.client.get(rv("gestion:api_stats"), {"metrique": "x'; DROP--", "periode": "../../etc"}, **ADMIN)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["metrique"], "actifs")
        self.assertEqual(r.json()["periode"], "30j")
        r = self.client.get(rv("gestion:api_stats"), {"periode": "perso", "debut": "n'importe", "fin": "quoi"}, **ADMIN)
        self.assertEqual(r.json()["periode"], "30j")

    def test_lien_video_non_https_refuse(self):
        data = self._donnees_cours()
        data["lecons-0-0-video_url"] = "javascript:alert(1)"
        r = self.post("gestion:cours_nouveau", data)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Cours.objects.filter(titre="Nouveau").exists())

    def test_fichier_non_image_refuse(self):
        data = self._donnees_cours()
        data["image"] = SimpleUploadedFile("x.png", b"<script>alert(1)</script>", content_type="image/png")
        self.assertEqual(self.post("gestion:cours_nouveau", data).status_code, 200)
        self.assertFalse(Cours.objects.filter(titre="Nouveau").exists())

    def test_video_de_bienvenue_envoyee_et_affichee(self):
        data = self._donnees_cours()
        data["video_bienvenue"] = SimpleUploadedFile("b.mp4", b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64, content_type="video/mp4")
        r = self.post("gestion:cours_nouveau", data)
        self.assertRedirects(r, rv("gestion:cours_liste"), fetch_redirect_response=False)
        c = Cours.objects.get(titre="Nouveau")
        self.assertTrue(c.video_bienvenue.name.startswith("videos-bienvenue/"))
        self.assertContains(self.client.get(c.get_absolute_url()), "<video")

    def test_faux_fichier_video_refuse(self):
        for nom, contenu in [("x.mp4", b"<script>alert(1)</script>"), ("x.exe", b"\x00\x00\x00\x18ftypmp42")]:
            data = self._donnees_cours()
            data["video_bienvenue"] = SimpleUploadedFile(nom, contenu, content_type="video/mp4")
            self.assertEqual(self.post("gestion:cours_nouveau", data).status_code, 200)
            self.assertFalse(Cours.objects.filter(titre="Nouveau").exists())

    def _donnees_cours(self):
        return {
            "titre": "Nouveau", "categorie": self.cours.categorie_id, "professeur": self.prof.pk,
            "image": SimpleUploadedFile("n.gif", GIF, content_type="image/gif"), "badge": "", "niveau": "Débutant",
            "duree": "1 h", "prix": "5", "ordre": "0", "publie": "on", "avec_modules": "True",
            "modules-TOTAL_FORMS": "1", "modules-INITIAL_FORMS": "0", "modules-MIN_NUM_FORMS": "0", "modules-MAX_NUM_FORMS": "1000",
            "modules-0-titre": "Débuter", "modules-0-ordre": "0",
            "lecons-0-TOTAL_FORMS": "1", "lecons-0-INITIAL_FORMS": "0", "lecons-0-MIN_NUM_FORMS": "0", "lecons-0-MAX_NUM_FORMS": "1000",
            "lecons-0-0-titre": "Intro", "lecons-0-0-ordre": "0", "lecons-0-0-video_url": "https://www.youtube.com/embed/abc",
        }

    def test_case_gratuit_ignore_les_prix(self):
        d = self._donnees_cours()
        d.update(gratuit="on", prix="", prix_barre="50", reduction="Remise")
        r = self.post("gestion:cours_nouveau", d)
        self.assertRedirects(r, rv("gestion:cours_liste"), fetch_redirect_response=False)
        c = Cours.objects.get(titre="Nouveau")
        self.assertEqual((c.prix, c.prix_barre, c.reduction), (0, None, ""))
        self.assertTrue(c.est_gratuit)

    def test_prix_obligatoire_si_pas_gratuit(self):
        d = self._donnees_cours()
        d["prix"] = ""
        self.assertEqual(self.post("gestion:cours_nouveau", d).status_code, 200)
        self.assertFalse(Cours.objects.filter(titre="Nouveau").exists())

    def test_creation_de_cours_avec_lecon(self):
        r = self.post("gestion:cours_nouveau", self._donnees_cours())
        self.assertRedirects(r, rv("gestion:cours_liste"), fetch_redirect_response=False)
        c = Cours.objects.get(titre="Nouveau")
        self.assertEqual(c.slug, "nouveau")
        self.assertEqual(c.auteur, "Awa")
        self.assertEqual(c.lecons.count(), 1)
        self.assertEqual(c.modules.get().titre, "Débuter")
        self.assertEqual(c.lecons.get().module, c.modules.get())


class PagesTests(BaseGestion):
    def setUp(self):
        super().setUp()
        self.connecter()

    def test_pages(self):
        Achat.objects.create(eleve=self.eleve, cours=self.cours, montant=10, statut=Achat.PAYE, paye_le=timezone.now())
        for nom, args in [("gestion:tableau_de_bord", ()), ("gestion:cours_liste", ()), ("gestion:cours_nouveau", ()),
                          ("gestion:cours_modifier", (self.cours.pk,)), ("gestion:cours_supprimer", (self.cours.pk,)),
                          ("gestion:etudiants_liste", ()), ("gestion:etudiant_detail", (self.eleve.pk,)), ("gestion:etudiant_modifier", (self.eleve.pk,)),
                          ("gestion:professeurs_liste", ()), ("gestion:professeur_nouveau", ()),
                          ("gestion:professeur_modifier", (self.prof.pk,)), ("gestion:ventes_liste", ()),
                          ("gestion:mot_de_passe", ())]:
            self.assertEqual(self.get(nom, *args).status_code, 200, nom)

    def test_les_comptes_equipe_ne_sont_pas_dans_les_etudiants(self):
        self.assertEqual(self.get("gestion:etudiant_detail", self.staff.pk).status_code, 404)
        self.assertEqual(self.post("gestion:etudiant_statut", args=[self.staff.pk]).status_code, 404)

    def test_desactiver_un_etudiant(self):
        self.post("gestion:etudiant_statut", args=[self.eleve.pk])
        self.eleve.refresh_from_db()
        self.assertFalse(self.eleve.is_active)

    def test_cours_achete_ne_se_supprime_pas(self):
        Achat.objects.create(eleve=self.eleve, cours=self.cours, montant=10, statut=Achat.PAYE)
        self.post("gestion:cours_supprimer", args=[self.cours.pk])
        self.assertTrue(Cours.objects.filter(pk=self.cours.pk).exists())

    def test_renommer_un_professeur_met_a_jour_ses_cours(self):
        self.post("gestion:professeur_modifier", {"nom": "Awa Diallo", "actif": "on"}, args=[self.prof.pk])
        self.cours.refresh_from_db()
        self.assertEqual(self.cours.auteur, "Awa Diallo")


class StatsTests(BaseGestion):
    def setUp(self):
        super().setUp()
        self.connecter()
        auj = timezone.localdate()
        autre = User.objects.create_user("autre", password=MDP)
        Activite.objects.create(eleve=self.eleve, jour=auj)
        Activite.objects.create(eleve=autre, jour=auj)
        Activite.objects.create(eleve=self.eleve, jour=auj - timedelta(days=2))
        SuiviCours.objects.create(eleve=self.eleve, cours=self.cours, jour=auj)
        SuiviCours.objects.create(eleve=autre, cours=self.cours, jour=auj)
        Achat.objects.create(eleve=self.eleve, cours=self.cours, montant=Decimal("10"), statut=Achat.PAYE, paye_le=timezone.now())

    def api(self, **p):
        return self.client.get(rv("gestion:api_stats"), p, **ADMIN).json()

    def test_etudiants_actifs(self):
        d = self.api(metrique="actifs", periode="7j")
        self.assertEqual(len(d["labels"]), 7)
        self.assertEqual(d["courbes"][0]["valeurs"][-1], 2)
        self.assertEqual(d["courbes"][0]["valeurs"][-3], 1)
        actifs = next(k for k in d["kpis"] if k["cle"] == "actifs")
        self.assertEqual(actifs["valeur"], 2)

    def test_cours_les_plus_suivis(self):
        d = self.api(metrique="cours", periode="30j")
        self.assertEqual(d["courbes"][0]["nom"], "Aquarelle")
        self.assertEqual(d["classement"][0]["nombre"], 2)

    def test_revenus_et_periode_annuelle_par_mois(self):
        d = self.api(metrique="revenus", periode="12m")
        self.assertEqual(d["granularite"], "mois")
        self.assertEqual(sum(d["courbes"][0]["valeurs"]), 10.0)

    def test_suivi_enregistre_a_l_ouverture_d_une_lecon(self):
        from academie.models import Lecon
        lecon = Lecon.objects.create(cours=self.cours, titre="L1", apercu=True)
        SuiviCours.objects.all().delete()
        self.client.force_login(self.eleve)
        self.client.get(lecon.get_absolute_url())
        self.assertEqual(SuiviCours.objects.filter(eleve=self.eleve, cours=self.cours).count(), 1)


class ModulesGestionTests(BaseGestion):
    """Modification d'un cours existant : modules et leçons imbriqués."""

    def setUp(self):
        super().setUp()
        self.connecter()
        from academie.models import Lecon, Module
        self.m = Module.objects.create(cours=self.cours, titre="Bases", ordre=0)
        self.l = Lecon.objects.create(cours=self.cours, module=self.m, titre="Intro", ordre=0)

    def _donnees(self, **plus):
        c = self.cours
        d = {
            "titre": c.titre, "categorie": c.categorie_id, "professeur": self.prof.pk, "badge": "", "niveau": "Débutant",
            "duree": "2 h", "prix": "10", "ordre": "0", "publie": "on", "avec_modules": "True",
            "modules-TOTAL_FORMS": "2", "modules-INITIAL_FORMS": "1", "modules-MIN_NUM_FORMS": "0", "modules-MAX_NUM_FORMS": "1000",
            "modules-0-id": self.m.pk, "modules-0-cours": c.pk, "modules-0-titre": "Bases", "modules-0-ordre": "0",
            "lecons-0-TOTAL_FORMS": "2", "lecons-0-INITIAL_FORMS": "1", "lecons-0-MIN_NUM_FORMS": "0", "lecons-0-MAX_NUM_FORMS": "1000",
            "lecons-0-0-id": self.l.pk, "lecons-0-0-module": self.m.pk, "lecons-0-0-titre": "Intro", "lecons-0-0-ordre": "0",
            "lecons-0-1-titre": "Deuxième", "lecons-0-1-ordre": "1", "lecons-0-1-video_url": "https://player.vimeo.com/video/1",
            "modules-1-titre": "Pratique", "modules-1-ordre": "1",
            "lecons-1-TOTAL_FORMS": "1", "lecons-1-INITIAL_FORMS": "0", "lecons-1-MIN_NUM_FORMS": "0", "lecons-1-MAX_NUM_FORMS": "1000",
            "lecons-1-0-titre": "Projet", "lecons-1-0-ordre": "0",
        }
        d.update(plus)
        return d

    def test_ajout_de_lecon_et_de_module(self):
        r = self.post("gestion:cours_modifier", self._donnees(), args=[self.cours.pk])
        self.assertRedirects(r, rv("gestion:cours_liste"), fetch_redirect_response=False)
        self.assertEqual([m.titre for m in self.cours.modules.all()], ["Bases", "Pratique"])
        self.assertEqual([l.titre for l in self.cours.lecons.all()], ["Intro", "Deuxième", "Projet"])
        self.assertEqual(self.cours.lecons.get(titre="Projet").module.titre, "Pratique")

    def test_suppression_de_module_supprime_ses_lecons(self):
        d = self._donnees(**{"modules-0-DELETE": "on", "modules-TOTAL_FORMS": "1"})
        self.post("gestion:cours_modifier", d, args=[self.cours.pk])
        self.assertEqual(self.cours.modules.count(), 0)
        self.assertEqual(self.cours.lecons.count(), 0)

    def test_page_de_modification_s_affiche_avec_les_modules(self):
        r = self.get("gestion:cours_modifier", self.cours.pk)
        self.assertContains(r, "Bases")
        self.assertContains(r, 'id="module-modele"')

    def test_passer_en_sans_module_regroupe_les_lecons_dans_l_ordre(self):
        d = self._donnees(avec_modules="False")
        self.post("gestion:cours_modifier", d, args=[self.cours.pk])
        self.cours.refresh_from_db()
        self.assertFalse(self.cours.avec_modules)
        self.assertEqual(self.cours.modules.count(), 1)
        self.assertEqual([l.titre for l in self.cours.lecons.all()], ["Intro", "Deuxième", "Projet"])
        self.assertEqual({l.module_id for l in self.cours.lecons.all()}, {self.cours.modules.get().pk})


class PhotosTests(BaseGestion):
    def setUp(self):
        super().setUp()
        self.connecter()

    def _donnees_etudiant(self, **extra):
        d = {"first_name": "Awa", "last_name": "Diop", "username": self.eleve.username, "email": "awa@test.com", "is_active": "on"}
        d.update(extra)
        return d

    def test_modifier_un_etudiant_avec_photo(self):
        d = self._donnees_etudiant(photo=SimpleUploadedFile("e.gif", GIF, content_type="image/gif"))
        r = self.post("gestion:etudiant_modifier", d, args=[self.eleve.pk])
        self.assertRedirects(r, rv("gestion:etudiant_detail", args=[self.eleve.pk]), fetch_redirect_response=False)
        self.eleve.refresh_from_db()
        self.assertEqual((self.eleve.first_name, self.eleve.email), ("Awa", "awa@test.com"))
        self.assertTrue(ProfilEleve.objects.get(eleve=self.eleve).photo.name.startswith("etudiants/"))
        self.assertContains(self.get("gestion:etudiants_liste"), "etudiants/")

    def test_decocher_actif_desactive_le_compte(self):
        d = self._donnees_etudiant()
        del d["is_active"]
        self.post("gestion:etudiant_modifier", d, args=[self.eleve.pk])
        self.eleve.refresh_from_db()
        self.assertFalse(self.eleve.is_active)

    def test_fausse_photo_et_email_en_double_refuses(self):
        d = self._donnees_etudiant(photo=SimpleUploadedFile("x.png", b"<script>", content_type="image/png"))
        self.assertEqual(self.post("gestion:etudiant_modifier", d, args=[self.eleve.pk]).status_code, 200)
        self.assertFalse(ProfilEleve.objects.filter(eleve=self.eleve).exclude(photo="").exists())
        d = self._donnees_etudiant(email=self.staff.email or "")
        if self.staff.email:
            self.assertEqual(self.post("gestion:etudiant_modifier", d, args=[self.eleve.pk]).status_code, 200)

    def test_un_compte_equipe_ne_se_modifie_pas_ici(self):
        self.assertEqual(self.get("gestion:etudiant_modifier", self.staff.pk).status_code, 404)

    def test_photo_professeur_affichee_sur_le_cours(self):
        self.prof.photo = SimpleUploadedFile("p.gif", GIF, content_type="image/gif")
        self.prof.save()
        self.cours.professeur = self.prof
        self.cours.save()
        self.assertContains(self.client.get(self.cours.get_absolute_url()), "hero__prof")


class CategoriesTests(BaseGestion):
    def setUp(self):
        super().setUp()
        self.connecter()

    def test_creer_une_categorie_genere_son_adresse(self):
        r = self.post("gestion:categorie_nouvelle", {"nom": "Intelligence artificielle", "ordre": "3"})
        self.assertRedirects(r, rv("gestion:categories_liste"), fetch_redirect_response=False)
        self.assertEqual(Categorie.objects.get(nom="Intelligence artificielle").slug, "intelligence-artificielle")
        self.post("gestion:categorie_nouvelle", {"nom": "Intelligence  artificielle!", "ordre": "0"})
        self.assertEqual(Categorie.objects.filter(slug__startswith="intelligence-artificielle").count(), 2)

    def test_nom_en_double_refuse(self):
        self.post("gestion:categorie_nouvelle", {"nom": "Langues", "ordre": "0"})
        r = self.post("gestion:categorie_nouvelle", {"nom": "langues", "ordre": "0"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Categorie.objects.filter(nom__iexact="langues").count(), 1)

    def test_categorie_avec_cours_ne_se_supprime_pas(self):
        self.post("gestion:categorie_supprimer", args=[self.cours.categorie_id])
        self.assertTrue(Categorie.objects.filter(pk=self.cours.categorie_id).exists())
        vide = Categorie.objects.create(nom="Vide", slug="vide")
        self.post("gestion:categorie_supprimer", args=[vide.pk])
        self.assertFalse(Categorie.objects.filter(pk=vide.pk).exists())

    def test_pages(self):
        self.assertEqual(self.get("gestion:categories_liste").status_code, 200)
        self.assertEqual(self.get("gestion:categorie_modifier", self.cours.categorie_id).status_code, 200)


class CoursSansModuleTests(BaseGestion):
    def setUp(self):
        super().setUp()
        self.connecter()

    def test_creation_d_un_cours_sans_module_avec_dix_lecons(self):
        d = {
            "titre": "Flat", "categorie": self.cours.categorie_id, "professeur": self.prof.pk, "avec_modules": "False",
            "image": SimpleUploadedFile("f.gif", GIF, content_type="image/gif"), "badge": "", "niveau": "Débutant",
            "duree": "1 h", "prix": "0", "ordre": "0", "publie": "on",
            "modules-TOTAL_FORMS": "1", "modules-INITIAL_FORMS": "0", "modules-MIN_NUM_FORMS": "0", "modules-MAX_NUM_FORMS": "1000",
            "modules-0-titre": "Contenu du cours", "modules-0-ordre": "0",  # champ caché, valeur par défaut
            "lecons-0-TOTAL_FORMS": "10", "lecons-0-INITIAL_FORMS": "0", "lecons-0-MIN_NUM_FORMS": "0", "lecons-0-MAX_NUM_FORMS": "1000",
        }
        for i in range(10):
            d[f"lecons-0-{i}-titre"] = f"Leçon {i + 1}"
            d[f"lecons-0-{i}-ordre"] = str(i)
        r = self.post("gestion:cours_nouveau", d)
        self.assertRedirects(r, rv("gestion:cours_liste"), fetch_redirect_response=False)
        c = Cours.objects.get(titre="Flat")
        self.assertFalse(c.avec_modules)
        self.assertEqual(c.modules.count(), 1)
        self.assertEqual([l.titre for l in c.lecons.all()], [f"Leçon {i}" for i in range(1, 11)])

    def test_le_choix_est_propose_dans_le_formulaire(self):
        r = self.get("gestion:cours_nouveau")
        self.assertContains(r, "Sans module")
        self.assertContains(r, "Avec modules")


@override_settings(ADMIN_2FA_REQUISE=False)
class SansDoubleAuthTests(BaseGestion):
    def test_le_mot_de_passe_suffit(self):
        r = self.client.post(rv("gestion:connexion"), {"username": "equipe", "password": MDP}, **ADMIN)
        self.assertRedirects(r, rv("gestion:tableau_de_bord"), fetch_redirect_response=False)
        self.assertEqual(self.get("gestion:tableau_de_bord").status_code, 200)

    def test_mauvais_mot_de_passe_toujours_refuse(self):
        r = self.client.post(rv("gestion:connexion"), {"username": "equipe", "password": "faux"}, **ADMIN)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.get("gestion:tableau_de_bord").status_code, 302)

    def test_un_etudiant_n_entre_toujours_pas(self):
        r = self.client.post(rv("gestion:connexion"), {"username": "eleve", "password": MDP}, **ADMIN)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.get("gestion:tableau_de_bord").status_code, 302)
