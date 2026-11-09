from decimal import Decimal

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Achat, Categorie, Cours, Inscription, Lecon, LeconTerminee, Module

# Plus petit GIF valide, pour ne pas dépendre de vraies images dans les tests
GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,"
    b"\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


@override_settings(MEDIA_ROOT="/tmp/sophos-tests-media", PAIEMENT_MODE="test")
class ParcoursEleveTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cat = Categorie.objects.create(nom="Dessin", slug="dessin")
        cls.cours = Cours.objects.create(
            categorie=cat, titre="Aquarelle", slug="aquarelle", duree="2 h", auteur="Atelier",
            prix=Decimal("0.50"), image=SimpleUploadedFile("a.gif", GIF, content_type="image/gif"),
            sur_accueil=True,
        )
        cls.apercu = Lecon.objects.create(cours=cls.cours, titre="Intro", ordre=0, apercu=True)
        cls.privee = Lecon.objects.create(cours=cls.cours, titre="Chapitre 1", ordre=1)
        cls.eleve = User.objects.create_user("eleve", "eleve@example.com", "mot-de-passe-test-123")

    def test_pages_publiques(self):
        for nom in ["accueil", "catalogue", "projets", "plus", "connexion", "inscription"]:
            self.assertEqual(self.client.get(reverse(nom)).status_code, 200, nom)
        self.assertContains(self.client.get(reverse("accueil")), "Aquarelle")
        self.assertContains(self.client.get(self.cours.get_absolute_url()), "Acheter 0,50 $")

    def test_carrousel_affiche_les_cours_en_vedette(self):
        cat = self.cours.categorie
        for i in range(5):
            Cours.objects.create(
                categorie=cat, titre=f"Vedette {i}", slug=f"vedette-{i}", duree="1 h", auteur="A",
                prix=Decimal("1"), image=self.cours.image.name, en_vedette=True, ordre=i,
            )
        r = self.client.get(reverse("accueil"))
        self.assertEqual(r.content.decode().count('class="carrousel__diapo"'), 5)
        self.assertEqual(r.content.decode().count('class="carrousel__point"'), 5)
        self.assertEqual(r.content.decode().count("<h1"), 1)

    def test_cours_non_publie_invisible(self):
        Cours.objects.filter(pk=self.cours.pk).update(publie=False)
        self.assertEqual(self.client.get(self.cours.get_absolute_url()).status_code, 404)
        self.assertNotContains(self.client.get(reverse("accueil")), "Aquarelle")

    def test_recherche(self):
        self.assertContains(self.client.get(reverse("catalogue"), {"q": "aquarelle"}), "Aquarelle")
        self.assertContains(self.client.get(reverse("catalogue"), {"q": "zzz"}), "Aucun cours")

    def test_apercu_libre_et_lecon_protegee(self):
        self.assertEqual(self.client.get(self.apercu.get_absolute_url()).status_code, 200)
        r = self.client.get(self.privee.get_absolute_url())
        self.assertRedirects(r, f"{reverse('connexion')}?next={self.privee.get_absolute_url()}")
        self.client.force_login(self.eleve)
        self.assertRedirects(self.client.get(self.privee.get_absolute_url()), self.cours.get_absolute_url())

    def test_achat_donne_acces(self):
        self.client.force_login(self.eleve)
        r = self.client.post(reverse("acheter", args=[self.cours.slug]))
        achat = Achat.objects.get(eleve=self.eleve)
        self.assertRedirects(r, reverse("paiement", args=[achat.reference]))
        self.assertEqual(achat.statut, Achat.EN_ATTENTE)

        self.client.post(reverse("paiement", args=[achat.reference]))
        achat.refresh_from_db()
        self.assertEqual(achat.statut, Achat.PAYE)
        self.assertEqual(self.client.get(self.privee.get_absolute_url()).status_code, 200)
        self.assertContains(self.client.get(reverse("mes_cours")), "Aquarelle")

    def test_achat_exige_connexion_et_post(self):
        self.assertEqual(self.client.post(reverse("acheter", args=[self.cours.slug])).status_code, 302)
        self.assertFalse(Achat.objects.exists())
        self.client.force_login(self.eleve)
        self.assertEqual(self.client.get(reverse("acheter", args=[self.cours.slug])).status_code, 405)

    def test_paiement_d_un_autre_eleve_interdit(self):
        achat = Achat.objects.create(eleve=self.eleve, cours=self.cours, montant=self.cours.prix)
        autre = User.objects.create_user("autre", "autre@example.com", "mot-de-passe-test-456")
        self.client.force_login(autre)
        self.assertEqual(self.client.post(reverse("paiement", args=[achat.reference])).status_code, 404)
        achat.refresh_from_db()
        self.assertEqual(achat.statut, Achat.EN_ATTENTE)

    @override_settings(PAIEMENT_MODE="cinetpay")
    def test_validation_test_desactivee_hors_mode_test(self):
        achat = Achat.objects.create(eleve=self.eleve, cours=self.cours, montant=self.cours.prix)
        self.client.force_login(self.eleve)
        self.assertEqual(self.client.post(reverse("paiement", args=[achat.reference])).status_code, 404)

    def test_inscription(self):
        r = self.client.post(reverse("inscription") + "?next=https://evil.example", {
            "first_name": "Awa", "username": "awa", "email": "awa@example.com",
            "password1": "Un-mot-de-passe-solide-1", "password2": "Un-mot-de-passe-solide-1",
        })
        self.assertRedirects(r, reverse("mes_cours"))
        self.assertTrue(User.objects.filter(username="awa").exists())

    def test_inscription_email_deja_utilise(self):
        r = self.client.post(reverse("inscription"), {
            "first_name": "X", "username": "x", "email": "ELEVE@example.com",
            "password1": "Un-mot-de-passe-solide-1", "password2": "Un-mot-de-passe-solide-1",
        })
        self.assertContains(r, "Un compte existe déjà")

    def test_admin_accessible_au_staff(self):
        admin = User.objects.create_superuser("admin", "admin@example.com", "mot-de-passe-test-789")
        self.client.force_login(admin)
        session = self.client.session
        session["gestion_2fa"] = admin.pk  # code du téléphone vérifié
        session.save()
        for url in ["admin:academie_cours_changelist", "admin:academie_achat_changelist", "admin:academie_projet_changelist"]:
            r = self.client.get(reverse(url, urlconf="sophos.urls_gestion"), HTTP_HOST="admin.localhost")
            self.assertEqual(r.status_code, 200, url)
        url = reverse("admin:academie_cours_change", args=[self.cours.pk], urlconf="sophos.urls_gestion")
        self.assertEqual(self.client.get(url, HTTP_HOST="admin.localhost").status_code, 200)


@override_settings(MEDIA_ROOT="/tmp/sophos-tests-media", PAIEMENT_MODE="test")
class ModulesInscriptionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cat = Categorie.objects.create(nom="Dessin", slug="dessin")
        img = lambda: SimpleUploadedFile("a.gif", GIF, content_type="image/gif")  # noqa: E731
        cls.payant = Cours.objects.create(categorie=cat, titre="Payant", slug="payant", duree="1 h", auteur="A", prix=Decimal("5"), image=img(), avec_modules=True)
        cls.gratuit = Cours.objects.create(categorie=cat, titre="Gratuit", slug="gratuit", duree="1 h", auteur="A", prix=Decimal("0"), image=img())
        cls.m1 = Module.objects.create(cours=cls.payant, titre="Bases", ordre=0)
        cls.m2 = Module.objects.create(cours=cls.payant, titre="Avancé", ordre=1)
        cls.l_accueil = Lecon.objects.create(cours=cls.payant, module=cls.m1, titre="Bienvenue", ordre=0, apercu=True)
        cls.l_2 = Lecon.objects.create(cours=cls.payant, module=cls.m1, titre="Matériel", ordre=1)
        cls.l_3 = Lecon.objects.create(cours=cls.payant, module=cls.m2, titre="Technique", ordre=0)
        cls.g1 = Lecon.objects.create(cours=cls.gratuit, module=Module.objects.create(cours=cls.gratuit, titre="Seul"), titre="Leçon gratuite")
        cls.eleve = User.objects.create_user("eleve", "e@x.fr", "mot-de-passe-test-123")

    def test_programme_par_modules_dans_l_ordre(self):
        r = self.client.get(self.payant.get_absolute_url())
        html = r.content.decode()
        self.assertLess(html.index("Bases"), html.index("Matériel"))
        self.assertLess(html.index("Matériel"), html.index("Avancé"))
        self.assertLess(html.index("Avancé"), html.index("Technique"))
        self.assertContains(r, "2 modules · 3 leçons")
        self.assertEqual(list(self.payant.lecons.all()), [self.l_accueil, self.l_2, self.l_3])

    def test_paiement_en_attente_ne_donne_pas_acces(self):
        self.client.force_login(self.eleve)
        self.client.post(reverse("acheter", args=["payant"]))
        self.assertFalse(Inscription.objects.exists())
        self.assertEqual(self.client.get(self.l_2.get_absolute_url()).status_code, 302)
        self.assertEqual(self.client.get(reverse("mes_cours")).context["inscriptions"], [])

    def test_apres_paiement_le_cours_est_dans_mes_cours_a_chaque_connexion(self):
        self.client.force_login(self.eleve)
        self.client.post(reverse("acheter", args=["payant"]))
        achat = Achat.objects.get(eleve=self.eleve, cours=self.payant)
        self.client.post(reverse("paiement", args=[achat.reference]))
        ins = Inscription.objects.get(eleve=self.eleve, cours=self.payant)
        self.assertFalse(ins.gratuite)
        self.assertEqual(ins.achat, achat)
        self.client.logout()  # nouvelle connexion plus tard
        self.client.force_login(self.eleve)
        self.assertContains(self.client.get(reverse("mes_cours")), "Payant")
        self.assertEqual(self.client.get(self.l_3.get_absolute_url()).status_code, 200)

    def test_cours_gratuit_inscription_directe(self):
        self.client.force_login(self.eleve)
        r = self.client.post(reverse("acheter", args=["gratuit"]))
        self.assertRedirects(r, self.g1.get_absolute_url(), fetch_redirect_response=False)
        self.assertTrue(Inscription.objects.get(eleve=self.eleve, cours=self.gratuit).gratuite)
        self.assertFalse(Achat.objects.exists())
        self.assertContains(self.client.get(reverse("mes_cours")), "Gratuit")
        self.client.post(reverse("s_inscrire", args=["gratuit"]))  # idempotent
        self.assertEqual(Inscription.objects.filter(eleve=self.eleve).count(), 1)

    def test_inscription_gratuite_impossible_sur_cours_payant(self):
        self.client.force_login(self.eleve)
        self.client.post(reverse("s_inscrire", args=["payant"]))
        self.assertFalse(Inscription.objects.exists())

    def test_inscription_exige_connexion(self):
        r = self.client.post(reverse("s_inscrire", args=["gratuit"]))
        self.assertEqual(r.status_code, 302)
        self.assertFalse(Inscription.objects.exists())

    def test_progression_et_reprise(self):
        Inscription.objects.create(eleve=self.eleve, cours=self.payant)
        self.client.force_login(self.eleve)
        r = self.client.post(reverse("lecon_terminer", args=["payant", self.l_accueil.pk]))
        self.assertRedirects(r, self.l_2.get_absolute_url(), fetch_redirect_response=False)
        page = self.client.get(reverse("mes_cours"))
        self.assertContains(page, "1 / 3 leçon")
        self.assertContains(page, "33 %")
        self.assertContains(page, self.l_2.get_absolute_url())  # « Reprendre » pointe vers la prochaine leçon
        self.client.post(reverse("lecon_terminer", args=["payant", self.l_2.pk]))
        r = self.client.post(reverse("lecon_terminer", args=["payant", self.l_3.pk]))
        self.assertRedirects(r, reverse("mes_cours"), fetch_redirect_response=False)
        self.assertContains(self.client.get(reverse("mes_cours")), "100 %")

    def test_terminer_sans_acces_refuse(self):
        self.client.force_login(self.eleve)
        r = self.client.post(reverse("lecon_terminer", args=["payant", self.l_2.pk]))
        self.assertEqual(r.status_code, 404)
        self.assertFalse(LeconTerminee.objects.exists())

    def test_migration_logique_lecon_sans_module(self):
        cours = self.payant
        lecon = Lecon.objects.create(cours=cours, titre="Orpheline")
        self.assertEqual(lecon.module.cours, cours)

    def test_cours_sans_module_affiche_une_simple_liste(self):
        flat = Cours.objects.create(categorie=self.payant.categorie, titre="Liste", slug="liste", duree="1 h", auteur="A", prix=0,
                                    image=SimpleUploadedFile("a.gif", GIF, content_type="image/gif"))
        for i in range(7):
            Lecon.objects.create(cours=flat, titre=f"Vidéo {i + 1}", ordre=i, apercu=(i == 0))
        r = self.client.get(flat.get_absolute_url())
        self.assertContains(r, "7 leçons")
        self.assertNotContains(r, "Module 1")
        self.assertNotContains(r, "Contenu du cours")
        # même page de leçon : sommaire sans titres de modules
        self.assertNotContains(self.client.get(flat.lecons.first().get_absolute_url()), "Contenu du cours")


class BasDePageEspaceEleveTests(TestCase):
    def test_pas_de_bandeau_dans_l_espace_eleve_mais_ailleurs(self):
        User.objects.create_user("eleve-x", password="pass12345!")
        self.client.login(username="eleve-x", password="pass12345!")
        self.assertNotContains(self.client.get("/mes-cours/"), 'class="bandeau"')
        self.assertContains(self.client.get("/mes-cours/"), 'class="pied"')
        self.assertContains(self.client.get("/"), 'class="bandeau"')


class LienVideoTests(TestCase):
    def test_liens_youtube_et_vimeo_convertis(self):
        casse = {
            "https://www.youtube.com/watch?v=BpVjUvmID4c": "https://www.youtube-nocookie.com/embed/BpVjUvmID4c",
            "https://www.youtube.com/watch?feature=share&v=BpVjUvmID4c&t=5": "https://www.youtube-nocookie.com/embed/BpVjUvmID4c",
            "https://youtu.be/BpVjUvmID4c?si=x": "https://www.youtube-nocookie.com/embed/BpVjUvmID4c",
            "https://www.youtube.com/embed/BpVjUvmID4c": "https://www.youtube-nocookie.com/embed/BpVjUvmID4c",
            "https://vimeo.com/123456": "https://player.vimeo.com/video/123456",
            "https://iframe.mediadelivery.net/embed/1/abc": "https://iframe.mediadelivery.net/embed/1/abc",
        }
        for entree, attendu in casse.items():
            self.assertEqual(Lecon(video_url=entree).video_integree, attendu, entree)


class ConnexionEmailTests(TestCase):
    def test_connexion_par_identifiant_ou_par_email(self):
        User.objects.create_user("compte-test", "compte@example.com", "Mdp-de-test-123")
        for ident in ["compte-test", "compte@example.com", "COMPTE@example.com"]:
            self.client.logout()
            r = self.client.post(reverse("connexion"), {"username": ident, "password": "Mdp-de-test-123"})
            self.assertEqual(r.status_code, 302, ident)
        self.client.logout()
        self.assertEqual(self.client.post(reverse("connexion"), {"username": "compte@example.com", "password": "faux"}).status_code, 200)

    def test_email_partage_par_deux_comptes_refuse(self):
        User.objects.create_user("a", "x@x.com", "pass12345!")
        User.objects.create_user("b", "x@x.com", "pass12345!")
        self.assertEqual(self.client.post(reverse("connexion"), {"username": "x@x.com", "password": "pass12345!"}).status_code, 200)
