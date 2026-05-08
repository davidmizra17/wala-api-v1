"""
Management command: seed_demo

Creates a realistic demo dataset that matches the Wala dashboard prototype:
  - 1 Tenant ("Flores Del Valle")
  - 1 Owner + 3 Agent users
  - 2 Channels (WhatsApp + Instagram)
  - 40 Contacts with Venezuelan names
  - ~130 Conversations (mix of statuses)
  - ~900 Messages spread across conversations
  - 1 Pipeline with 63 Deals spread across all 5 stages
  - Tasks attached to deals

Run once on a fresh DB:
    python manage.py seed_demo

Re-runnable: skips if Tenant slug already exists.
"""

import random
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from tenants.models import Tenant
from channels.models import Channel
from contacts.models import Contact
from conversations.models import Conversation, Message
from crm.models import Pipeline, Deal, Task

User = get_user_model()

FIRST_NAMES = [
    "Carolina", "Luis", "Andreína", "Rodrigo", "Verónica", "Gabriel",
    "María", "José", "Ana", "Carlos", "Laura", "Pedro", "Sofía", "Miguel",
    "Valentina", "Andrés", "Isabella", "Juan", "Daniela", "Fernando",
    "Mariana", "Ricardo", "Camila", "Alejandro", "Paula", "Nicolás",
    "Diana", "Jorge", "Lucía", "Sergio", "Patricia", "Roberto", "Elena",
    "Antonio", "Natalia", "Eduardo", "Carmen", "Héctor", "Gabriela", "Tomás",
]

LAST_NAMES = [
    "Pérez", "Meléndez", "Silva", "Ibarra", "Mata", "Torres", "García",
    "Rodríguez", "Martínez", "López", "González", "Hernández", "Díaz",
    "Ramírez", "Morales", "Jiménez", "Vargas", "Castillo", "Ramos", "Ortega",
]

DEAL_TITLES = [
    "Arreglo floral boda", "Decoración quinceañera", "Centro de mesa bautizo",
    "Ramo novia premium", "Flores evento corporativo", "Corona fúnebre",
    "Decoración cumpleaños", "Arreglo San Valentín", "Canasta de flores",
    "Bouquet ejecutivo", "Decoración grado", "Flores aniversario",
    "Arreglo navideño", "Centro mesa restaurante", "Flores día de la madre",
]

TASK_TITLES = [
    "Llamar para confirmar entrega", "Enviar cotización por WhatsApp",
    "Confirmar fecha del evento", "Revisar disponibilidad de flores",
    "Coordinar transporte", "Seguimiento de pago",
    "Enviar foto del arreglo terminado", "Agendar reunión con cliente",
]

MESSAGE_TEXTS_INBOUND = [
    "Hola, quisiera información sobre arreglos florales.",
    "¿Tienen disponibilidad para el sábado?",
    "¿Cuánto cuesta un ramo de rosas?",
    "Me pueden enviar fotos de sus trabajos?",
    "Quiero hacer un pedido para una boda.",
    "¿Hacen entregas a domicilio?",
    "Buenos días, necesito un arreglo para mañana.",
    "¿Trabajan con claveles?",
    "Cuánto demoran en preparar un pedido grande?",
    "Estoy interesada en decoración para quinceañera.",
]

MESSAGE_TEXTS_OUTBOUND = [
    "¡Hola! Con gusto te ayudamos. ¿Para qué ocasión es el arreglo?",
    "Sí, tenemos disponibilidad. ¿Para cuántas personas?",
    "Los ramos de rosas tienen un precio desde $25. ¿Te gustaría ver opciones?",
    "Por supuesto, te envío fotos ahora mismo.",
    "Para bodas tenemos paquetes especiales. ¿Cuándo es el evento?",
    "Sí, hacemos entregas. ¿Cuál es la dirección?",
    "Podemos tenerlo listo en 2 horas. ¿Confirmas el pedido?",
    "Trabajamos con claveles colombianos de primera calidad.",
    "Para pedidos grandes, necesitamos al menos 3 días de anticipación.",
    "Tenemos hermosos paquetes para quinceañeras. Te paso los detalles.",
]


class Command(BaseCommand):
    help = "Seed demo data for the Wala dashboard"

    def handle(self, *args, **options):
        if Tenant.objects.filter(slug="flores-del-valle").exists():
            self.stdout.write(self.style.WARNING("Demo data already exists. Skipping."))
            return

        self.stdout.write("Seeding demo data...")

        tenant = self._create_tenant()
        owner, agents = self._create_users(tenant)
        channels = self._create_channels(tenant)
        contacts = self._create_contacts(tenant, channels)
        conversations = self._create_conversations(tenant, contacts, channels, agents)
        self._create_messages(tenant, conversations)
        self._create_pipeline_and_deals(tenant, contacts, conversations, agents)

        self.stdout.write(self.style.SUCCESS(
            f"Done. Tenant: {tenant.name} | "
            f"Contacts: {Contact.objects.filter(tenant=tenant).count()} | "
            f"Conversations: {Conversation.objects.filter(tenant=tenant).count()} | "
            f"Messages: {Message.objects.filter(tenant=tenant).count()} | "
            f"Deals: {Deal.objects.filter(tenant=tenant).count()}"
        ))

    # ------------------------------------------------------------------ #

    def _create_tenant(self):
        tenant = Tenant.objects.create(
            name="Flores Del Valle",
            slug="flores-del-valle",
            subscription=Tenant.Subscription.STARTER,
            is_active=True,
        )
        self.stdout.write(f"  Tenant: {tenant.name}")
        return tenant

    def _create_users(self, tenant):
        owner = User.objects.create_user(
            email="maria@floresdelvalle.com",
            password="demo1234",
            tenant=tenant,
            role=User.Role.OWNER,
            is_staff=True,
        )
        agents = []
        agent_data = [
            ("andres@floresdelvalle.com", "Andrés"),
            ("sofia@floresdelvalle.com", "Sofía"),
            ("miguel@floresdelvalle.com", "Miguel"),
        ]
        for email, name in agent_data:
            agent = User.objects.create_user(
                email=email,
                password="demo1234",
                tenant=tenant,
                role=User.Role.AGENT,
            )
            agents.append(agent)
        self.stdout.write(f"  Users: 1 owner + {len(agents)} agents")
        return owner, agents

    def _create_channels(self, tenant):
        wa = Channel.objects.create(
            tenant=tenant,
            platform=Channel.Platform.WHATSAPP,
            name="WhatsApp Principal",
            wa_phone_id="100000000000001",
            wa_token="demo-token-wa",
            verify_token="demo-verify-wa",
            is_active=True,
        )
        ig = Channel.objects.create(
            tenant=tenant,
            platform=Channel.Platform.INSTAGRAM,
            name="Instagram @floresdelvalle",
            is_active=True,
        )
        self.stdout.write("  Channels: WhatsApp + Instagram")
        return [wa, ig]

    def _create_contacts(self, tenant, channels):
        contacts = []
        used_names = set()
        for i in range(40):
            first = random.choice(FIRST_NAMES)
            last = random.choice(LAST_NAMES)
            while (first, last) in used_names:
                first = random.choice(FIRST_NAMES)
                last = random.choice(LAST_NAMES)
            used_names.add((first, last))

            platform_choice = random.choices(
                [Contact.Platform.WHATSAPP, Contact.Platform.INSTAGRAM],
                weights=[82, 18],
            )[0]
            contact = Contact.objects.create(
                tenant=tenant,
                external_id=f"ext_{i+1:04d}",
                name=f"{first} {last}",
                phone=f"+584{random.randint(10,29)}{random.randint(1000000,9999999)}",
                platform=platform_choice,
                tags=random.sample(["vip", "boda", "quinceañera", "empresa", "regular"], k=random.randint(0, 2)),
            )
            contacts.append(contact)
        self.stdout.write(f"  Contacts: {len(contacts)}")
        return contacts

    def _create_conversations(self, tenant, contacts, channels, agents):
        wa_channel, ig_channel = channels
        conversations = []

        # Target: ~130 conversations → ~924 bot + ~360 human messages
        # Status distribution: 60 bot_handling, 40 human_handling, 30 closed
        status_pool = (
            [Conversation.Status.BOT_HANDLING] * 60 +
            [Conversation.Status.HUMAN_HANDLING] * 40 +
            [Conversation.Status.CLOSED] * 30
        )
        random.shuffle(status_pool)

        for i, contact in enumerate(contacts):
            n_convos = random.randint(2, 5)
            for j in range(n_convos):
                status = status_pool[i % len(status_pool)]
                channel = wa_channel if contact.platform == Contact.Platform.WHATSAPP else ig_channel
                assigned = random.choice(agents) if status == Conversation.Status.HUMAN_HANDLING else None
                conv = Conversation.objects.create(
                    tenant=tenant,
                    contact=contact,
                    channel=channel,
                    status=status,
                    assigned_to=assigned,
                )
                conversations.append(conv)

        self.stdout.write(f"  Conversations: {len(conversations)}")
        return conversations

    def _create_messages(self, tenant, conversations):
        msgs = []
        for conv in conversations:
            n_msgs = random.randint(4, 12)
            for k in range(n_msgs):
                is_inbound = (k % 2 == 0)
                if is_inbound:
                    direction = Message.Direction.INBOUND
                    sender_type = Message.SenderType.CONTACT
                    text = random.choice(MESSAGE_TEXTS_INBOUND)
                else:
                    direction = Message.Direction.OUTBOUND
                    sender_type = random.choice([Message.SenderType.BOT, Message.SenderType.HUMAN])
                    text = random.choice(MESSAGE_TEXTS_OUTBOUND)

                msgs.append(Message(
                    tenant=tenant,
                    conversation=conv,
                    text=text,
                    direction=direction,
                    sender_type=sender_type,
                ))

        Message.objects.bulk_create(msgs)
        self.stdout.write(f"  Messages: {len(msgs)}")

    def _create_pipeline_and_deals(self, tenant, contacts, conversations, agents):
        pipeline = Pipeline.objects.create(tenant=tenant, name="Pipeline Principal")

        # Target counts per stage to match dashboard prototype
        stage_config = [
            (Deal.Stage.NEW,       24),
            (Deal.Stage.CONTACTED, 18),
            (Deal.Stage.QUALIFIED,  9),
            (Deal.Stage.WON,        7),
            (Deal.Stage.LOST,       5),
        ]

        deal_index = 0
        tasks = []
        today = date.today()

        for stage, count in stage_config:
            for _ in range(count):
                contact = contacts[deal_index % len(contacts)]
                conv = conversations[deal_index % len(conversations)] if conversations else None
                value = round(random.uniform(80, 600), 2)

                deal = Deal.objects.create(
                    tenant=tenant,
                    pipeline=pipeline,
                    contact=contact,
                    title=random.choice(DEAL_TITLES),
                    stage=stage,
                    value=value,
                    conversation=conv,
                )

                # Add 1-3 tasks per deal
                for _ in range(random.randint(1, 3)):
                    due = today + timedelta(days=random.randint(-3, 14))
                    tasks.append(Task(
                        tenant=tenant,
                        deal=deal,
                        title=random.choice(TASK_TITLES),
                        due_date=due,
                        assigned_to=random.choice(agents),
                        is_done=random.random() < 0.35,
                    ))

                deal_index += 1

        Task.objects.bulk_create(tasks)
        self.stdout.write(
            f"  Pipeline: '{pipeline.name}' | "
            f"Deals: {Deal.objects.filter(tenant=tenant).count()} | "
            f"Tasks: {Task.objects.filter(tenant=tenant).count()}"
        )
